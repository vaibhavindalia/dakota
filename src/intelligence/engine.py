"""Central Intelligence Engine for Dakota: Grounded RAG, Pipeline & Citation Synthesizer."""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Iterator

from src.intelligence.conversations import add_message, get_conversation_history
from src.intelligence.models import (
    Citation,
    ClaimFinding,
    EvidenceItem,
    EvidenceType,
    IntelligenceAnswer,
    IntelligenceQuery,
    ObservationType,
    TimelineEvent,
)
from src.intelligence.prompt_sanitizer import (
    format_evidence_block,
    sanitize_untrusted_text,
)
from src.intelligence.provider import DeterministicReasoningEngine, get_ai_provider
from src.intelligence.retriever import IntelligenceRetriever

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Dakota Intelligence Core, an institutional AI investigation and forensic analysis copilot.
Your purpose is to assist financial analysts, compliance investigators, and market researchers in evaluating equities, news events, social rumors, and coordinated campaign patterns.

CRITICAL OPERATIONAL RULES:
1. STRICT GROUNDING: You must answer using ONLY the facts and data provided in the VERIFIED EVIDENCE STORE below.
2. ABSOLUTE ZERO HALLUCINATION: Never invent stock prices, news headlines, SEBI orders, Telegram messages, or evidence records.
3. PRESERVE CITATIONS: Whenever you state a fact or claim, attach the corresponding evidence citation tag (e.g. [E1], [E2]).
4. DISTINGUISH TRUTH STATES: Explicitly distinguish directly observed facts (e.g. exchange trading data, published news articles) from interpretations and unverified rumors.
5. IDENTIFY CONFLICTS: If two sources disagree (e.g. promotional hype claiming a 500% target vs negative earnings in news), explicitly highlight the contradiction.
6. STATE UNCERTAINTIES HONESTLY: If data is missing or a connector is unconfigured, state the limitation clearly rather than pretending it was checked.
7. COMPLIANCE & LEGAL SAFETY: Never accuse an entity of fraud without citing official regulatory enforcement action. Use phrases like "elevated risk indicators observed" or "in line with SEBI cautionary parameters". Do not give financial advice.
"""


class IntelligenceEngine:
    """Orchestrates intent extraction, multi-source retrieval, grounded reasoning, and verifiable citation binding."""

    def __init__(self) -> None:
        self.retriever = IntelligenceRetriever()

    def process_query(self, query_req: IntelligenceQuery) -> IntelligenceAnswer:
        """Execute complete synchronous query answering with citation binding."""
        query_text = sanitize_untrusted_text(query_req.query)
        cid = query_req.conversation_id or str(uuid.uuid4())
        active_ctx = query_req.active_context or {}

        # 1. Multi-source Grounded Retrieval
        evidence_items = self.retriever.retrieve(
            query=query_text,
            context=active_ctx,
            max_evidence=12,
        )

        # 2. Build Passive Evidence Block & Prompt
        ev_dicts = [item.model_dump() for item in evidence_items]
        evidence_block = format_evidence_block(ev_dicts) if ev_dicts else "No verified evidence items were retrieved."

        # Fetch conversation history for session context
        history = get_conversation_history(cid, limit=6)
        history_str = ""
        if history:
            history_lines = ["\nPRIOR CONVERSATION CONTEXT:"]
            for m in history[-4:]:
                history_lines.append(f"{m['role'].upper()}: {sanitize_untrusted_text(m['content'])[:300]}")
            history_str = "\n".join(history_lines) + "\n"

        prompt = f"""{evidence_block}

{history_str}
USER QUESTION: {query_text}

INSTRUCTIONS:
Provide a rigorous, professional intelligence briefing addressing the question above.
Cite every specific point with its evidence identifier (e.g. [E1], [E2]).
Highlight any contradictions between promotional hype and fundamentals.
Point out data limitations where applicable.
"""

        # 3. Provider Generation
        provider = get_ai_provider()
        prov_status = provider.get_status()

        try:
            gen_result = provider.generate_response(
                prompt=prompt,
                system_instruction=SYSTEM_PROMPT,
                temperature=0.2,
            )
            raw_text = gen_result.get("text", "")
        except Exception as exc:
            logger.warning("Provider generation error (%s); falling back to grounded deterministic engine", exc)
            fallback = DeterministicReasoningEngine(reason=f"Live provider fallback: {exc}")
            gen_result = fallback.generate_response(
                prompt=prompt,
                system_instruction=SYSTEM_PROMPT,
                temperature=0.2,
            )
            raw_text = gen_result.get("text", "")
            prov_status = fallback.get_status()

        # 4. Citation and Claim Extraction
        citations = self._bind_citations(raw_text, evidence_items)
        findings = self._extract_findings(evidence_items)
        contradictions = self._detect_contradictions(evidence_items)
        timeline = self._build_timeline(evidence_items)
        followups = self._generate_followups(query_text, evidence_items)
        limitations = self._derive_limitations(evidence_items, prov_status)

        # Executive summary is first 2 paragraphs
        paras = [p.strip() for p in raw_text.split("\n\n") if p.strip()]
        summary = paras[0] if paras else "Analysis completed on retrieved Dakota evidence."

        # Confidence calculation
        confidence_score = 0.95 if any(e.type in (EvidenceType.MARKET, EvidenceType.REGULATORY) for e in evidence_items) else 0.80
        if not evidence_items:
            confidence_score = 0.50

        answer = IntelligenceAnswer(
            query=query_text,
            conversation_id=cid,
            summary=summary,
            detailed_text=raw_text,
            findings=findings,
            evidence_items=evidence_items,
            citations=citations,
            contradictions=contradictions,
            timeline=timeline,
            confidence_score=confidence_score,
            confidence_rationale="High confidence based on direct SQLite equity data and RSS news feeds." if confidence_score > 0.85 else "Standard confidence; based on unverified social feeds or limited evidence.",
            unknowns_and_limitations=limitations,
            suggested_followups=followups,
            next_investigative_steps=[
                "Cross-examine SEBI surveillance database for recent GSM/ASM actions.",
                "Review promoter shareholding pattern and pledged percentage in financial reports.",
                "Inspect related syndicate campaigns across monitored Telegram channels.",
            ],
            provider_info=prov_status,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

        # 5. Persist to Conversation Store
        try:
            add_message(
                conversation_id=cid,
                role="user",
                content=query_text,
            )
            add_message(
                conversation_id=cid,
                role="assistant",
                content=raw_text,
                citations=[c.model_dump() for c in citations],
                evidence=[e.model_dump() for e in evidence_items],
            )
        except Exception as exc:
            logger.warning("Could not persist message to SQLite: %s", exc)

        return answer

    def stream_query(self, query_req: IntelligenceQuery) -> Iterator[str]:
        """Server-Sent Events (SSE) generator yielding chunks, then final metadata envelope."""
        query_text = sanitize_untrusted_text(query_req.query)
        cid = query_req.conversation_id or str(uuid.uuid4())
        active_ctx = query_req.active_context or {}

        evidence_items = self.retriever.retrieve(
            query=query_text,
            context=active_ctx,
            max_evidence=12,
        )

        ev_dicts = [item.model_dump() for item in evidence_items]
        evidence_block = format_evidence_block(ev_dicts) if ev_dicts else "No verified evidence items were retrieved."

        history = get_conversation_history(cid, limit=4)
        history_str = ""
        if history:
            history_lines = ["\nPRIOR CONVERSATION CONTEXT:"]
            for m in history:
                history_lines.append(f"{m['role'].upper()}: {sanitize_untrusted_text(m['content'])[:300]}")
            history_str = "\n".join(history_lines) + "\n"

        prompt = f"""{evidence_block}

{history_str}
USER QUESTION: {query_text}

INSTRUCTIONS:
Provide a rigorous, professional intelligence briefing addressing the question above.
Cite every specific point with its evidence identifier (e.g. [E1], [E2]).
Highlight any contradictions between promotional hype and fundamentals.
Point out data limitations where applicable.
"""

        provider = get_ai_provider()
        full_text_chunks: list[str] = []

        # Yield retrieved evidence summary upfront
        initial_event = {
            "type": "retrieval_complete",
            "conversation_id": cid,
            "evidence_count": len(evidence_items),
            "evidence_items": [e.model_dump() for e in evidence_items],
            "provider": provider.get_status(),
        }
        yield f"data: {json.dumps(initial_event)}\n\n"

        try:
            for chunk in provider.stream_response(prompt=prompt, system_instruction=SYSTEM_PROMPT):
                full_text_chunks.append(chunk)
                chunk_event = {"type": "content_chunk", "chunk": chunk}
                yield f"data: {json.dumps(chunk_event)}\n\n"
        except Exception as exc:
            logger.warning("Provider stream error (%s); streaming from deterministic engine fallback", exc)
            fallback = DeterministicReasoningEngine(reason=f"Live stream fallback: {exc}")
            for chunk in fallback.stream_response(prompt=prompt, system_instruction=SYSTEM_PROMPT):
                full_text_chunks.append(chunk)
                chunk_event = {"type": "content_chunk", "chunk": chunk}
                yield f"data: {json.dumps(chunk_event)}\n\n"

        complete_text = "".join(full_text_chunks)
        citations = self._bind_citations(complete_text, evidence_items)
        findings = self._extract_findings(evidence_items)
        contradictions = self._detect_contradictions(evidence_items)
        followups = self._generate_followups(query_text, evidence_items)
        limitations = self._derive_limitations(evidence_items, provider.get_status())

        final_event = {
            "type": "done",
            "conversation_id": cid,
            "citations": [c.model_dump() for c in citations],
            "findings": [f.model_dump() for f in findings],
            "contradictions": contradictions,
            "followups": followups,
            "limitations": limitations,
        }
        yield f"data: {json.dumps(final_event)}\n\n"

        # Persist conversation
        try:
            add_message(cid, "user", query_text)
            add_message(
                cid,
                "assistant",
                complete_text,
                citations=[c.model_dump() for c in citations],
                evidence=[e.model_dump() for e in evidence_items],
            )
        except Exception:
            pass

    def _bind_citations(self, text: str, evidence_items: list[EvidenceItem]) -> list[Citation]:
        """Find citation tags like [E1], [E2] in generated text and associate with actual evidence items."""
        ev_map = {e.id: e for e in evidence_items}
        found_tags = re.findall(r"\[(E\d+)\]", text)
        citations: list[Citation] = []
        seen: set[str] = set()

        for idx, tag in enumerate(found_tags, start=1):
            if tag in ev_map and tag not in seen:
                seen.add(tag)
                item = ev_map[tag]
                citations.append(
                    Citation(
                        index=idx,
                        evidence_id=tag,
                        label=f"[{tag}]",
                        source_name=item.source_name,
                        source_url=item.source_url,
                        snippet=item.snippet[:200],
                        observation_type=item.observation_type.value,
                    )
                )

        # If model did not emit tags but evidence was retrieved, create citations for the top 3 items
        if not citations and evidence_items:
            for idx, item in enumerate(evidence_items[:3], start=1):
                citations.append(
                    Citation(
                        index=idx,
                        evidence_id=item.id,
                        label=f"[{item.id}]",
                        source_name=item.source_name,
                        source_url=item.source_url,
                        snippet=item.snippet[:200],
                        observation_type=item.observation_type.value,
                    )
                )

        return citations

    def _extract_findings(self, evidence_items: list[EvidenceItem]) -> list[ClaimFinding]:
        findings: list[ClaimFinding] = []
        for e in evidence_items:
            if e.type in (EvidenceType.REGULATORY, EvidenceType.MARKET, EvidenceType.INVESTIGATION):
                findings.append(
                    ClaimFinding(
                        claim=e.snippet[:140],
                        status="directly_observed" if e.verified else "unverified_claim",
                        supporting_evidence_ids=[e.id],
                        severity="high" if "High" in e.snippet or "scam" in e.snippet.lower() else "low",
                        confidence=e.confidence,
                    )
                )
        return findings[:5]

    def _detect_contradictions(self, evidence_items: list[EvidenceItem]) -> list[str]:
        contradictions: list[str] = []
        has_promotional_hype = any(
            e.type == EvidenceType.SOCIAL or "scam" in e.snippet.lower() or "target" in e.snippet.lower()
            for e in evidence_items
        )
        has_negative_fundamentals = any(
            "High" in e.snippet or "CRITICAL_AVOID" in e.snippet or "FAIL" in e.snippet
            for e in evidence_items
        )

        if has_promotional_hype and has_negative_fundamentals:
            contradictions.append(
                "Divergence detected: Aggressive promotional targets/social buzz contradict high forensic risk scores or critical technical stance."
            )

        return contradictions

    def _build_timeline(self, evidence_items: list[EvidenceItem]) -> list[TimelineEvent]:
        events: list[TimelineEvent] = []
        for e in evidence_items:
            if e.published_at:
                date_clean = e.published_at[:10]
                events.append(
                    TimelineEvent(
                        date=date_clean,
                        title=e.title[:60],
                        description=e.snippet[:120],
                        evidence_id=e.id,
                    )
                )
        return sorted(events, key=lambda x: x.date, reverse=True)[:5]

    def _generate_followups(self, query: str, evidence_items: list[EvidenceItem]) -> list[str]:
        tickers = [e.entity_id for e in evidence_items if e.entity_id]
        primary = tickers[0] if tickers else None

        if primary:
            return [
                f"Why did {primary}'s risk score reach its current band?",
                f"What recent news stories relate to {primary}?",
                f"Show the evidence behind the investment stance for {primary}.",
                f"Generate a comprehensive intelligence brief for {primary}.",
            ]

        return [
            "Summarize the highest-risk securities currently flagged in Dakota.",
            "Are there any coordinated promotional cartels active in monitored channels?",
            "How does my portfolio's forensic risk compare across holdings?",
            "What important evidence has changed recently?",
        ]

    def _derive_limitations(self, evidence_items: list[EvidenceItem], prov_status: dict[str, Any]) -> list[str]:
        limitations: list[str] = []
        if not any(e.type == EvidenceType.NEWS for e in evidence_items):
            limitations.append("News RSS returned limited headlines for this specific symbol.")
        if not any(e.type == EvidenceType.SOCIAL for e in evidence_items):
            limitations.append("Social discovery was restricted to public search indexing; direct private feeds are access-gated.")
        if not prov_status.get("is_live"):
            limitations.append("AI reasoning executed via Dakota's native deterministic forensic engine.")
        return limitations
