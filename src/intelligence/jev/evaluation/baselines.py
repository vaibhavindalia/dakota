"""Non-LLM and Frontier Baselines for Fair Comparative Evaluation.

Implements:
1. MajorityClassBaseline: Empirical training-set prior distribution.
2. TfidfLogisticRegressionBaseline: Scikit-learn TF-IDF + balanced Logistic Regression.
3. FrontierReferenceBaseline: OpenAI GPT-4o/5.5 API adapter with calibrated fallback.
"""
from __future__ import annotations

import collections
import os
import time
from typing import Any, Dict, List, Optional, Sequence
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from ..schemas import PredictionResult, compute_prompt_hash


class MajorityClassBaseline:
    """Predicts the most frequent class observed in the training split.
    
    Provides an essential null-hypothesis baseline. Any viable model must decisively beat this.
    """

    def __init__(self, classes: Sequence[str]):
        self.classes = list(classes)
        self.majority_label: str = self.classes[0]
        self.prior_distribution: Dict[str, float] = {c: 1.0 / len(self.classes) for c in self.classes}
        self.is_fitted: bool = False

    def fit(self, train_samples: Sequence[Dict[str, Any]], label_key: str = "label") -> None:
        counts = collections.Counter(s[label_key] for s in train_samples)
        total = sum(counts.values())
        if total == 0:
            return

        # Laplace smoothing to avoid zero probabilities
        k = len(self.classes)
        smoothed_total = total + k
        self.prior_distribution = {
            c: round((counts.get(c, 0) + 1.0) / smoothed_total, 4) for c in self.classes
        }
        self.majority_label = counts.most_common(1)[0][0]
        self.is_fitted = True

    def predict_one(self, sample: Dict[str, Any]) -> PredictionResult:
        t0 = time.perf_counter()
        probs = dict(self.prior_distribution)
        conf = probs[self.majority_label]

        # Margin vs runner-up
        sorted_probs = sorted(probs.values(), reverse=True)
        margin = sorted_probs[0] - sorted_probs[1] if len(sorted_probs) > 1 else 0.0

        lat = (time.perf_counter() - t0) * 1000.0

        return PredictionResult(
            task_name="majority_class_baseline",
            predicted_label=self.majority_label,
            class_scores=probs,
            confidence=round(conf, 4),
            is_calibrated=True,
            margin=round(margin, 4),
            model_id="baseline:majority_class",
            classifier_version="baseline-v1.0",
            prompt_hash="none",
            dataset_version="baseline",
            latency_ms=round(lat, 4),
        )

    def predict_batch(self, samples: Sequence[Dict[str, Any]]) -> List[PredictionResult]:
        return [self.predict_one(s) for s in samples]


def extract_sample_text(sample: Dict[str, Any]) -> str:
    """Concatenate verbal features from sample dictionary for text featurization."""
    parts = []
    ticker = sample.get("ticker", "")
    if ticker:
        parts.append(f"Ticker: {ticker}")

    claim = sample.get("claim", "") or sample.get("claim_text", "")
    if claim:
        parts.append(f"Claim: {claim}")

    news = sample.get("news_headlines", [])
    if news:
        parts.append("News: " + " | ".join(news))

    social = sample.get("social_signals", [])
    if social:
        parts.append("Social: " + " | ".join(social))

    risk_band = sample.get("risk_band")
    if risk_band:
        parts.append(f"Risk: {risk_band}")

    technicals = sample.get("technicals", {})
    if isinstance(technicals, dict):
        trend = technicals.get("trend_vs_ema20")
        if trend:
            parts.append(f"Trend: {trend}")

    return " ".join(parts)


class TfidfLogisticRegressionBaseline:
    """Scikit-Learn TF-IDF + Multinomial Logistic Regression baseline.
    
    Serves as the classical NLP baseline to quantify the value added by language models.
    """

    def __init__(self, classes: Sequence[str]):
        self.classes = list(classes)
        self.vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            max_features=1000,
            sublinear_tf=True,
        )
        self.classifier = LogisticRegression(
            class_weight="balanced",
            max_iter=500,
            random_state=42,
        )
        self.is_fitted: bool = False

    def fit(self, train_samples: Sequence[Dict[str, Any]], label_key: str = "label") -> None:
        texts = [extract_sample_text(s) for s in train_samples]
        labels = [s[label_key] for s in train_samples]

        X = self.vectorizer.fit_transform(texts)
        self.classifier.fit(X, labels)
        self.is_fitted = True

    def predict_one(self, sample: Dict[str, Any]) -> PredictionResult:
        if not self.is_fitted:
            raise RuntimeError("Model must be fit before calling predict")

        t0 = time.perf_counter()
        text = extract_sample_text(sample)
        X = self.vectorizer.transform([text])
        pred_label = self.classifier.predict(X)[0]
        prob_vec = self.classifier.predict_proba(X)[0]

        # Map to class probabilities dict
        model_classes = list(self.classifier.classes_)
        prob_dict = {c: 0.0 for c in self.classes}
        for cls_name, p in zip(model_classes, prob_vec):
            prob_dict[cls_name] = float(p)

        conf = prob_dict[pred_label]
        sorted_probs = sorted(prob_dict.values(), reverse=True)
        margin = sorted_probs[0] - sorted_probs[1] if len(sorted_probs) > 1 else 0.0

        lat = (time.perf_counter() - t0) * 1000.0

        return PredictionResult(
            task_name="tfidf_logreg_baseline",
            predicted_label=pred_label,
            class_scores=prob_dict,
            confidence=round(conf, 4),
            is_calibrated=False,
            margin=round(margin, 4),
            model_id="baseline:tfidf_logreg",
            classifier_version="baseline-v1.0",
            prompt_hash=compute_prompt_hash(text),
            dataset_version="baseline",
            latency_ms=round(lat, 2),
        )

    def predict_batch(self, samples: Sequence[Dict[str, Any]]) -> List[PredictionResult]:
        return [self.predict_one(s) for s in samples]


class FrontierReferenceBaseline:
    """Frontier Reference Model (OpenAI GPT-4o / GPT-5.5).
    
    If OPENAI_API_KEY is available, issues standard zero-shot / few-shot prompts to the live API.
    Does NOT peek at ground truth. Raises an explicit error if OPENAI_API_KEY is not configured.
    """

    def __init__(self, model_id: str = "gpt-4o", classes: Optional[Sequence[str]] = None):
        self.model_id = model_id
        self.classes = list(classes) if classes else [
            "Bullish", "Bearish", "Neutral", "Mixed", "Insufficient Evidence"
        ]
        self.api_key = os.getenv("OPENAI_API_KEY")

    def predict_one(self, sample: Dict[str, Any]) -> PredictionResult:
        t0 = time.perf_counter()

        if not self.api_key:
            raise ValueError(
                "OPENAI_API_KEY is not configured. Deceptive ground-truth peeking has been removed. "
                "For authentic local GPU comparative evaluation, use QwenGenerativeBaseline instead."
            )

        import openai
        client = openai.OpenAI(api_key=self.api_key)
        text = extract_sample_text(sample)
        prompt = (
            f"Analyze the following Indian equity evidence and classify sentiment into exactly one of: "
            f"{', '.join(self.classes)}.\n\nContext:\n{text}\n\nClassification:"
        )
        resp = client.chat.completions.create(
            model=self.model_id,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=10,
            temperature=0.0,
        )
        pred_label = resp.choices[0].message.content.strip()
        matched = self.classes[0]
        for c in self.classes:
            if c.lower() in pred_label.lower():
                matched = c
                break

        lat = (time.perf_counter() - t0) * 1000.0
        return PredictionResult(
            task_name="frontier_reference",
            predicted_label=matched,
            class_scores={c: (0.85 if c == matched else 0.15 / (len(self.classes) - 1)) for c in self.classes},
            confidence=0.85,
            is_calibrated=False,
            margin=0.70,
            model_id=f"frontier:{self.model_id}",
            classifier_version="frontier-v1.0",
            prompt_hash=compute_prompt_hash(prompt),
            dataset_version="frontier",
            latency_ms=round(lat, 2),
        )

    def predict_batch(self, samples: Sequence[Dict[str, Any]]) -> List[PredictionResult]:
        return [self.predict_one(s) for s in samples]


class QwenGenerativeBaseline:
    """Authentic Local Generative Baseline running autoregressive token generation (N > 0).

    Uses the exact same local Qwen model checkpoint as JEV, but executes standard
    autoregressive decoding (model.generate(max_new_tokens=25)) on the RTX 4060 GPU.
    Provides a scientifically fair head-to-head comparison:
    - JEV ($N = 0$ tokens generated, single prefix forward pass) vs.
    - Generative ($N \\approx 15-25$ tokens generated, sequential autoregressive decode loops).
    """

    def __init__(
        self,
        model_id: str = "Qwen/Qwen2.5-0.5B-Instruct",
        classes: Optional[Sequence[str]] = None,
        adapter: Optional[Any] = None,
        device: str = "cuda",
        load_in_4bit: bool = False,
        enable_thinking: bool = False,
        max_new_tokens: int = 64,
        baseline_label: str = "fair_generative",
    ):
        self.model_id = model_id
        self.classes = list(classes) if classes else [
            "Bullish", "Bearish", "Neutral", "Mixed", "Insufficient Evidence"
        ]
        self._adapter = adapter
        self.device = device
        self.load_in_4bit = load_in_4bit
        self.enable_thinking = enable_thinking
        self.max_new_tokens = max_new_tokens
        self.baseline_label = baseline_label
        self._model = None
        self._tokenizer = None

    def _ensure_loaded(self) -> None:
        if self._adapter is not None:
            if not self._adapter.is_loaded():
                self._adapter.load_model()
            self._model = self._adapter._model
            self._tokenizer = self._adapter._tokenizer
            return

        if self._model is None:
            from ..adapters.hf_adapter import HuggingFaceQwenAdapter
            self._adapter = HuggingFaceQwenAdapter(
                model_id=self.model_id,
                device=self.device,
                load_in_4bit=self.load_in_4bit,
            )
            self._adapter.load_model()
            self._model = self._adapter._model
            self._tokenizer = self._adapter._tokenizer

    def predict_one(self, sample: Dict[str, Any]) -> Tuple[PredictionResult, int]:
        """Runs autoregressive generation on the Qwen model. Returns (PredictionResult, tokens_generated)."""
        self._ensure_loaded()
        import torch

        t0 = time.perf_counter()
        text = extract_sample_text(sample)
        prompt = (
            f"Analyze the following Indian equity market evidence and classify the prevailing sentiment "
            f"into exactly one of the candidate classes: {', '.join(self.classes)}.\n\n"
            f"Context:\n{text}\n\n"
            f"Reply with the single candidate class name only:"
        )

        messages = [
            {"role": "system", "content": "You are a professional financial equity analyst."},
            {"role": "user", "content": prompt},
        ]
        chat_kwargs = {"tokenize": False, "add_generation_prompt": True}
        try:
            formatted = self._tokenizer.apply_chat_template(
                messages,
                enable_thinking=self.enable_thinking,
                **chat_kwargs,
            )
        except TypeError:
            # Tokenizer does not support enable_thinking argument
            formatted = self._tokenizer.apply_chat_template(messages, **chat_kwargs)

        inputs = self._tokenizer(formatted, return_tensors="pt")
        dev = next(self._model.parameters()).device
        input_ids = inputs["input_ids"].to(dev)
        attention_mask = inputs["attention_mask"].to(dev)

        with torch.no_grad():
            output_tokens = self._model.generate(
                input_ids=input_ids,
                attention_mask=attention_mask,
                max_new_tokens=self.max_new_tokens,
                temperature=0.0,
                do_sample=False,
                pad_token_id=self._tokenizer.pad_token_id or self._tokenizer.eos_token_id,
            )

        gen_tokens = output_tokens[0][input_ids.shape[1]:]
        n_tokens_gen = len(gen_tokens)
        gen_text = self._tokenizer.decode(gen_tokens, skip_special_tokens=True).strip()

        # Parse generated answer strictly against permitted candidate classes
        gen_lower = gen_text.lower()
        matched: Optional[str] = None
        for c in self.classes:
            if c.lower() in gen_lower:
                matched = c
                break

        lat = (time.perf_counter() - t0) * 1000.0

        if matched is not None:
            top_conf = 0.70
            rem_p = (1.0 - top_conf) / (len(self.classes) - 1)
            prob_dict = {c: (top_conf if c == matched else rem_p) for c in self.classes}
            pred_label = matched
        else:
            # Genuine malformed or unanswered response: mark as abstained/malformed, do not invent class
            uniform_p = 1.0 / len(self.classes)
            prob_dict = {c: uniform_p for c in self.classes}
            pred_label = "Malformed/Abstained"
            top_conf = uniform_p

        res = PredictionResult(
            task_name=f"qwen_{self.baseline_label}",
            predicted_label=pred_label,
            class_scores=prob_dict,
            confidence=top_conf,
            is_calibrated=False,
            margin=0.0 if pred_label not in self.classes else round(top_conf - ((1.0 - top_conf)/(len(self.classes)-1)), 4),
            model_id=f"generative:{self.model_id}:{self.baseline_label}",
            classifier_version="generative-v2.0",
            prompt_hash=compute_prompt_hash(formatted),
            dataset_version="baseline",
            latency_ms=round(lat, 2),
        )
        return res, n_tokens_gen

    def predict_batch(self, samples: Sequence[Dict[str, Any]]) -> Tuple[List[PredictionResult], List[int]]:
        results = []
        token_counts = []
        for s in samples:
            res, n_tok = self.predict_one(s)
            results.append(res)
            token_counts.append(n_tok)
        return results, token_counts
