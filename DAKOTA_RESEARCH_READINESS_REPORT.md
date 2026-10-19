# DAKOTA — RESEARCH READINESS & DATA QUALITY REPORT

**Audit Date**: 2026-10-19 14:21:20 UTC  
**Evaluation Standard**: Academic Research & Financial NLP Benchmark Defensibility  
**Overall Status**: **PASS WITH LIMITATIONS (READY FOR BASELINE RESEARCH)**

---

## 1. Research Quality Gate Verification

| Quality Gate | Requirement | Measured Result | Verdict |
| :--- | :--- | :--- | :---: |
| **1. ID Integrity** | Unique, stable, sequential `ANN-LIVE-001` .. `082` | 82 unique IDs, 0 duplicates, 0 gaps | **PASS** |
| **2. Schema Completeness** | Required fields populated across all records | 100% complete core schema | **PASS** |
| **3. Ground Truth Separation** | AI suggestions strictly isolated from human labels | `human_reviewed_label` contains only 1 human review (`REV-VAIBHAV`). 0 AI labels leaked into ground truth. | **PASS** |
| **4. Group-Aware Splitting** | Zero duplicate-group cross-contamination | `dev_groups ∩ held_out_groups = ∅`. Zero record leakage. | **PASS** |
| **5. Input Isolation** | Held-out reference labels omitted from model prompts | Evaluator passes only context & evidence, never reference labels. | **PASS** |
| **6. Non-Financial Control** | Non-financial messages explicitly flagged | 25 records flagged as negative controls. | **PASS** |
| **7. Evidence Sufficiency** | Ground truth volume sufficient for publication claims | 1/82 human reviewed. Dev benchmark ready; full statistical held-out test requires completing review queue. | **WARNING (Documented Limitation)** |

---

## 2. Leakage-Safe Data Splits

The 60 duplicate groups were partitioned using deterministic random seed `42`:

- **Development Split (`dev`)**:
  - **Records**: 53 records (64.6%)
  - **Duplicate Groups**: 39 unique groups (65.0%)
  - **Human Labeled Records**: 1 record (`ANN-LIVE-001`: `Insufficient Evidence`)
  - **AI Pre-Annotated Distribution**: Bullish (10), Bearish (2), Neutral (1), Mixed (1), Insufficient Evidence (39).
- **Held-Out Evaluation Split (`held_out`)**:
  - **Records**: 29 records (35.4%)
  - **Duplicate Groups**: 21 unique groups (35.0%)
  - **Human Labeled Records**: 0 (pending human exception review)
  - **AI Pre-Annotated Distribution**: Bullish (5), Neutral (1), Insufficient Evidence (23).
- **Cross-Split Leakage**: Exactly **0 records** and **0 groups** overlap.

---

## 3. Prioritized Exception Review Queue

Rather than requiring tedious manual entry for all 82 records, human review is organized into an exception queue (`data/research/annotation_review_queue.csv`):

1. **Tier 1 — High Conflict / Non-Financial Controls (26 records)**:
   - 1 Conflicting record (`ANN-LIVE-059` Suzlon with mixed signals).
   - 25 Non-financial records from `@minish_fast` and general chat to confirm negative-control status.
2. **Tier 2 — High-Impact Verified Equity Events (12 records)**:
   - Specific ticker recommendations with attached news (CDSL, TCS, Zomato, Suzlon, IRCTC). Requires human verification of whether news warrants directional label or abstention.
3. **Tier 3 — Routine Corporate Disclosures & Forum Threads (16 records)**:
   - General forum threads or routine disclosures.
4. **Tier 4 — Routine Uncorroborated Promotional Spam (28 records)**:
   - Isolated telegram calls with zero external evidence. Eligible for batch confirmation as `Insufficient Evidence`.

---

## 4. Research Defensibility Verdict

The dataset infrastructure **PASSES** all technical research-readiness criteria. Baselines and model evaluations can be executed immediately against the development split and exploratory pre-annotated benchmark. 

Claims of final generalization to the broader Indian stock market remain out of scope until held-out human annotation is completed.
