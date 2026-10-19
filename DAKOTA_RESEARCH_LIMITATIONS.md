# DAKOTA — RESEARCH LIMITATIONS, ETHICAL BOUNDARIES & SCIENTIFIC HONESTY

**Document Version**: 1.0.0  
**Date**: October 19, 2026  
**Status**: ACTIVE RESEARCH DOCUMENTATION  
**Project**: Dakota Intelligence Platform  

---

## 1. Scope and Sampling Limitations

1. **Convenience Sampling, Not Whole-Market Representation**:
   - The 82 records currently inventoried in Dakota originate from a single intake period on **October 8, 2026**, capturing public Telegram channels (`@markemahakelpredictions`, `@Growx_intraday_groww`, etc.).
   - This cohort is a **convenience sample** of high-activity retail stock tips and social discussions. It does **not** represent a statistically valid or uniform random sample of the National Stock Exchange of India (NSE) or Bombay Stock Exchange (BSE).
   - Findings from this cohort cannot be generalized to broad-market price movements, institutional trading desks, or all Indian listed securities.

2. **Truncation of Raw Text Bodies**:
   - The initial ingestion pipeline structured messages into key attributes (`Source | Entity | Target Price | Urgency | Type`), discarding long conversational threads, image attachments, and voice notes.
   - Models are evaluating these structured claim summaries rather than full multimodal chat histories.

3. **External Corroboration Sparsity**:
   - Only 30 of the 82 records (36.6%) have attached external sources (Reddit discussions, Google News headlines, BSE filings).
   - 52 records (63.4%) are isolated Telegram strings without external corroboration. This reflects real-world social intelligence conditions, where the vast majority of social tips lack verifiable corporate filings.

---

## 2. Statistical & Evaluative Limitations

1. **Ground Truth Sample Size**:
   - At the time of this audit, exactly **1 record** (`ANN-LIVE-001`) has completed formal human expert review (confirmed as `Insufficient Evidence` by `REV-VAIBHAV`).
   - The remaining 81 records have deterministic AI suggested pre-annotations (`ai_suggested_label`). While these provide an exploratory testbed for baseline comparisons, **claims of true held-out model accuracy must wait until human reviews are completed across the held-out split**.

2. **Severe Class Imbalance**:
   - Uncorroborated promotional claims dominate the dataset, leading to an `Insufficient Evidence` prevalence of ~65%.
   - A naive majority-class baseline that constantly predicts `Insufficient Evidence` achieves ~65% raw accuracy while contributing zero discriminative utility (Macro F1 ~ 0.13).
   - Evaluators must prioritize **Macro F1, Balanced Accuracy, and Per-Class Recall** over raw accuracy.

3. **Statistical Confidence Intervals**:
   - Due to $N = 82$, 95% Wilson score confidence intervals for accuracy span approximately $\pm 10\%$.
   - Any observed metric difference smaller than $\pm 8\%$ between models cannot be claimed as statistically significant without expanding the sample size.

---

## 3. Legal, Ethical, and Forensic Boundaries

1. **Suspicion vs. Legal Proof**:
   - A promotional message, aggressive price target, or unusual social chatter constitutes an **anomaly indicator**, NOT legal proof of unlawful market manipulation under SEBI (Prohibition of Fraudulent and Unfair Trade Practices Relating to Securities Market) Regulations, 2003.
   - Dakota's models characterize textual and evidentiary divergence; they do not render legal or regulatory judgments.

2. **Non-Financial Negative Controls**:
   - 25 of the 82 records are non-financial chatter (e.g., administrative announcements from `@minish_fast`).
   - Models must abstain (`Insufficient Evidence`) rather than forcing a directional bullish or bearish sentiment on non-market text.

3. **Absence of Proof ≠ Proof of Falsity**:
   - When external evidence is missing, the proper classification is `Insufficient Evidence`. The system must never falsely claim a prediction is disproven merely because corroborating filings could not be retrieved.

---

## 4. Hardware & Inference Constraints

1. **Inference Latency without Fused Kernels**:
   - On the local NVIDIA GeForce RTX 4060 Laptop GPU (8GB VRAM), Qwen3.5-9B runs in 4-bit NF4 precision.
   - In the absence of specialized CUDA kernels (`causal_conv1d`, `flash-linear-attention`), the linear attention layers fall back to standard PyTorch reference operations, yielding per-sample latencies of 10–25 seconds.
   - While adequate for offline batch research and development probes, high-throughput production streaming will require optimized kernel installation or vLLM deployment in future phases.

2. **Safe Defaults Preserved**:
   - The operational default `DAKOTA_USE_JEV=0` remains in effect to safeguard CPU-based and development workflows against accidental GPU memory exhaustion.
