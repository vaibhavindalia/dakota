# Dakota Phase 3.1 — Human Annotation Protocol and Evaluation Guidelines

**Document Version:** 1.0.0  
**Target Environment:** Indian Financial Equities and Surveillance Evidence  
**Author:** ML Evaluation Engineering Team  
**Dataset Artifact:** `data/annotation_ready_financial_evidence.json`  
**Tooling Script:** `scripts/annotate_financial_evidence.py`  

---

## 1. Objective and Research Scope

Under the Dakota Research Blueprint (Whiteboard Architecture), Dakota integrates market microstructure telemetry, exchange filings, corporate news, and social chatter to detect suspicious equity activity and classify market sentiment. 

To benchmark the JEV (Joint Energy-based Verification) Qwen3.5-9B model against classical baselines reliably, **evaluation must be conducted against human-verified ground truth**, not synthetic mocks or ungrounded price heuristics.

This document defines the official human annotation protocol, label taxonomy, decision boundaries, and quality control procedures for annotating the 82 live Indian market records (`ANN-LIVE-001` through `ANN-LIVE-082`).

---

## 2. The 6 Canonical Classification Classes

All annotations must map strictly to one of the six canonical classes:

```
[1] Bullish
[2] Bearish
[3] Neutral
[4] Mixed
[5] Ambiguous
[6] Insufficient Evidence
```

### Detailed Decision Rubric

| Class | Definition & Criteria | Concrete Indian Market Examples |
| :--- | :--- | :--- |
| **Bullish** | Strong verifiable evidence of operational growth, earnings beat, substantial order wins, institutional accumulation, debt reduction, or positive regulatory clearance. | *"Infosys posts 14% net profit increase in Q2; raises full-year constant currency guidance."*<br>*"L&T secures ₹4,500 Cr mega EPC infrastructure contract from domestic client."* |
| **Bearish** | Verifiable evidence of financial deterioration, loss-making quarters, SEBI investigation or penalty notices, auditor resignations, forensic accounting red flags, or exchange surveillance actions. | *"Vedanta issued ₹500 Cr penalty notice by tax authorities; board orders internal audit."*<br>*"SEBI issues interim order against promoters for fraudulent diversion of corporate funds."* |
| **Neutral** | Factual corporate communication or balanced market report that conveys ordinary operations with no clear positive or negative directional bias. | *"TCS notifies exchanges of scheduled board meeting on October 14 for dividend consideration."*<br>*"HDFC Bank shares trade flat in range-bound market following RBI policy status quo."* |
| **Mixed** | Verifiable coexistence of conflicting directional evidence of comparable significance (e.g. operational strength alongside regulatory penalty or speculative divergence). | *"Suzlon reports 25% revenue surge and positive operating cash flow, but net debt rises due to capex."*<br>*"Promotional social media channels heavily push CDSL while exchange data shows delivery volume collapse and GSM surveillance placement."* |
| **Ambiguous** | The available context contains credible but undecidable claims, speculative rumors of equal weight, or conflicting brokerage targets without consensus. | *"Brokerage A assigns Buy with ₹1,800 target citing cloud acceleration; Brokerage B downgrades to Sell with ₹1,300 citing margin compression."*<br>*"Market chatter suggests potential merger, but both companies decline to comment."* |
| **Insufficient Evidence** | The record lacks verifiable factual context, company financial disclosures, or exchange telemetry. Includes unactionable promotional tips, spam, or claims referencing untraceable tickers. | *"Join VIP Telegram group for guaranteed 1000% jackpot intraday stocks daily!"*<br>*"Buy immediately, huge breakout coming tomorrow!" (No company name, no facts, no filings).* |

---

## 3. Critical Boundary Distinctions

To ensure high inter-annotator agreement and consistent benchmark semantics, annotators must adhere to three mandatory boundary distinctions:

### A. Insufficient Evidence vs. Neutral
- **Neutral** contains *verifiable factual information* that describes normal corporate operations or market balance without directional bias (e.g. AGM date notice, routine statutory disclosure, range-bound trading).
- **Insufficient Evidence** lacks *actionable factual grounding* entirely. An uncorroborated social media tout ("Buy now, double your money!") has no verified facts and must **never** be labeled as Neutral or Bullish.

### B. Mixed vs. Ambiguous
- **Mixed** occurs when *two or more verified facts point in opposite directions* (e.g., positive revenue beat coupled with a major regulatory investigation). Both directional forces are real and confirmed.
- **Ambiguous** occurs when the information itself is *undecidable or contradictory without clear factual grounding* (e.g. split analyst price targets of identical credibility, or contradictory rumors neither confirmed nor denied).

### C. Promotional Social Claims vs. Verified Disclosures
- Social media chatter, Telegram alerts, and forum posts are **unverified claims**, not facts.
- If a social tip touts a stock without corroborating exchange filings or credible news, classify as **Insufficient Evidence**.
- If a social tip promotes a stock aggressively while official exchange telemetry shows collapsing delivery volume or active surveillance (GSM/ASM), classify as **Mixed** (promotional touting diverging from deteriorating fundamentals).
- Never label an uncorroborated promotional post as "Bullish" solely because the author claims the price will rise.

---

## 4. Annotation Tooling & Workflow

Dakota provides a dedicated script: `scripts/annotate_financial_evidence.py`.

### A. Check Progress
```bash
python scripts/annotate_financial_evidence.py status
```
Displays completed, pending, and flagged record counts, label distribution, reviewer contributions, and duplicate group consistency.

### B. Interactive CLI Annotation
```bash
python scripts/annotate_financial_evidence.py annotate --reviewer REV-01
```
Features:
- Displays ticker, duplicate group, timestamp, evidence IDs, original text, news headlines, sources, and telemetry.
- Prompts for canonical label [1-6], Flag [F], Skip [S], Back [B], or Quit [Q].
- Requires a non-empty `annotation_rationale` explaining the human decision.
- Immediately executes atomic writes with backup (`.bak`).

### C. Spreadsheet / CSV Workflow (Excel / Google Sheets)
1. Export worklist to CSV:
   ```bash
   python scripts/annotate_financial_evidence.py export-csv --output data/annotation_worklist.csv
   ```
2. Open `data/annotation_worklist.csv` in Excel or Google Sheets.
3. Complete `human_reviewed_label`, `annotation_rationale`, and `reviewer_id`.
4. Import and validate:
   ```bash
   python scripts/annotate_financial_evidence.py import-csv --input data/annotation_worklist.csv
   ```
   *Strict validator enforces canonical labels, non-empty rationales, and preserves all IDs.*

---

## 5. Dataset Splitting & Event Leakage Prevention

To ensure evaluation integrity, dataset records are grouped by `duplicate_group` (fingerprinted by source, entity, and publication window):
- **46 single-record clusters**
- **14 multi-record clusters** (covering 36 records)

### Strict Splitting Rule:
Records belonging to the same `duplicate_group` **must always reside in the same split** (either Dev or Held-Out). Splitting identical or near-duplicate events across train/dev and test causes severe data leakage and invalidates benchmark claims.

To export leakage-free splits once annotation is complete:
```bash
python scripts/annotate_financial_evidence.py export-splits --dev-ratio 0.65
```
This produces:
- `data/financial_eval_dev.json` (~65% of duplicate groups)
- `data/financial_eval_held_out.json` (~35% of duplicate groups)
- Mathematically guarantees `dev_groups ∩ held_out_groups = ∅`.

---

## 6. Safety & Integrity Invariants

1. **No Automated Label Injection:** Model predictions must never be automatically converted into human ground-truth labels.
2. **Mandatory Rationales:** Every human label must be accompanied by an explanatory rationale citing the specific evidence.
3. **Preservation of Provenance:** Stable IDs (`ANN-LIVE-xxx`), source URLs, and evidence IDs (`E_xxx`) must never be modified or removed during annotation.
4. **Separation of Pending vs Completed:** Unreviewed records remain strictly flagged as `pending` and are excluded from evaluation metrics until reviewed.
