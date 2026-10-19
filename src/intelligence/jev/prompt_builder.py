"""Prompt builder for JEV classification engine.

Implements the v1 prompt construction specification shared by Simple JEV.
Ensures deterministic prompt compilation across different inference backends.
"""
from __future__ import annotations

import json
import string
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

from .schemas import ClassifierQuestion, ClassifierRequest, QuestionType

DEFAULT_TEMPLATE_VERSION = "v1"
CHOICE_LABELS = string.ascii_uppercase + string.ascii_lowercase[:24]

# Constant system prompt prefix for v1
SYSTEM_PROMPT_PREFIX = (
    "You are a precise classification engine. Evaluate the context and answer "
    "each question by selecting the exact candidate label that matches the evidence."
)


def canonical_json(value: Any) -> str:
    """Deterministically serialize structured context into stable JSON.
    
    Sorted keys and compact separators ensure prompt hashes are 100% reproducible.
    """
    if isinstance(value, str):
        return value
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


@dataclass(frozen=True)
class ScoringQuestion:
    """Compiled question branch prepared for logit readout."""
    question_id: str
    branch_id: str
    type: QuestionType
    instruction: str
    answer_prefix: str
    output_labels: Tuple[str, ...]
    answer_labels: Tuple[str, ...]


@dataclass
class PromptPlan:
    """Execution plan containing compiled prompt segments and scoring branches."""
    template_version: str
    system_prompt_prefix: str
    prefix_instruction: str
    suffix_instruction: str
    state_text: Optional[str]
    messages: Optional[List[Dict[str, str]]]
    questions: List[ScoringQuestion]
    raw_request: ClassifierRequest


def prepare_prompt(request: Union[ClassifierRequest, Dict[str, Any]], version: str = DEFAULT_TEMPLATE_VERSION) -> PromptPlan:
    """Compile request into a deterministic PromptPlan."""
    if isinstance(request, dict):
        req = ClassifierRequest.model_validate(request)
    else:
        req = request

    if version != "v1":
        raise ValueError(f"Unsupported prompt template version: {version!r}. Only 'v1' is supported.")

    branches: List[ScoringQuestion] = []
    for idx, (qid, q) in enumerate(req.questions.items()):
        branch_id = str(idx)
        if q.type == QuestionType.CHOICE:
            if not q.criteria or len(q.criteria) < 2:
                raise ValueError(f"Choice question {qid!r} must have at least 2 criteria candidates.")
            if len(q.criteria) > len(CHOICE_LABELS):
                raise ValueError(f"Choice question {qid!r} exceeds maximum supported choices ({len(CHOICE_LABELS)}).")

            candidate_keys = list(q.criteria.keys())
            assigned_labels = tuple(CHOICE_LABELS[:len(candidate_keys)])
            
            # Format options block
            lines = [q.instructions.strip(), "", "Candidates:"]
            for lbl, cand in zip(assigned_labels, candidate_keys):
                desc = q.criteria[cand]
                if desc:
                    lines.append(f"({lbl}) {cand} — {desc}")
                else:
                    lines.append(f"({lbl}) {cand}")
            lines.append("")
            lines.append("Select the single best candidate by replying with its letter label only.")
            
            instruction_text = "\n".join(lines)
            answer_prefix = "Answer: ("
            
            branches.append(
                ScoringQuestion(
                    question_id=qid,
                    branch_id=branch_id,
                    type=q.type,
                    instruction=instruction_text,
                    answer_prefix=answer_prefix,
                    output_labels=assigned_labels,
                    answer_labels=tuple(candidate_keys),
                )
            )

        elif q.type == QuestionType.SCORE:
            if not q.criteria or len(q.criteria) < 2:
                raise ValueError(f"Score question {qid!r} must have at least 2 rubric levels.")

            levels = list(q.criteria.keys())
            assigned_labels = tuple(str(i) for i in range(len(levels)))
            
            lines = [q.instructions.strip(), "", "Rubric Levels:"]
            for lvl_idx, (lvl, desc) in enumerate(q.criteria.items()):
                lines.append(f"Level {lvl_idx}: {lvl} — {desc or ''}")
            lines.append("")
            lines.append("Assign the integer score corresponding to the matching level.")
            
            instruction_text = "\n".join(lines)
            answer_prefix = "Score: "
            
            branches.append(
                ScoringQuestion(
                    question_id=qid,
                    branch_id=branch_id,
                    type=q.type,
                    instruction=instruction_text,
                    answer_prefix=answer_prefix,
                    output_labels=assigned_labels,
                    answer_labels=tuple(levels),
                )
            )

        elif q.type == QuestionType.NOUL:
            # 9-bin continuous probability rating (digits 1 to 9)
            assigned_labels = tuple(str(i) for i in range(1, 10))
            lines = [
                q.instructions.strip(),
                "",
                "Rate your certainty or probability of this condition on a scale from 1 (lowest, ~10%) to 9 (highest, ~90%).",
            ]
            instruction_text = "\n".join(lines)
            answer_prefix = "Rating: "
            
            branches.append(
                ScoringQuestion(
                    question_id=qid,
                    branch_id=branch_id,
                    type=q.type,
                    instruction=instruction_text,
                    answer_prefix=answer_prefix,
                    output_labels=assigned_labels,
                    answer_labels=assigned_labels,
                )
            )

    state_str = canonical_json(req.state) if req.state is not None else None

    return PromptPlan(
        template_version=version,
        system_prompt_prefix=SYSTEM_PROMPT_PREFIX,
        prefix_instruction="Contextual Evidence State:\n",
        suffix_instruction="\nEvaluation Question:\n",
        state_text=state_str,
        messages=req.messages,
        questions=branches,
        raw_request=req,
    )
