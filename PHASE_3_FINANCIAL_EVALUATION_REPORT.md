# DAKOTA PHASE 3 — REAL FINANCIAL-DATA EVALUATION REPORT

**Author**: Senior ML Evaluation Engineer (Financial NLP, Calibration, & Reproducible Systems)  
**Date**: October 19, 2026  
**Git Branch**: `feature/integrate-official-simple-jev`  
**Base Commit**: `49f360e` (Integration audit & regression fixes) / `20bc74a`  
**Target Architecture**: Featherless AI Simple JEV (v1 Specification) + Qwen3.5-9B 4-bit NF4  
**Runtime Hardware**: NVIDIA GeForce RTX 4060 Laptop GPU (8.00 GiB VRAM), 16 GiB Host RAM, WSL2 Ubuntu 22.04 LTS  
**Primary Artifact**: [`scripts/evaluate_financial_evidence.py`](file:///d:/dakota%20V4%20with%20telegram%20integrated/dakota%20integ.%20d11%20final%20prototype1%20minus%20telegram%20feature/dakota/scripts/evaluate_financial_evidence.py)  
**Evaluation Dataset**: Curated Held-Out Benchmark Dataset (Indian Equity, 7 Samples)  
**Annotation Template**: [`data/annotation_ready_financial_evidence.json`](file:///d:/dakota%20V4%20with%20telegram%20integrated/dakota%20integ.%20d11%20final%20prototype1%20minus%20telegram%20feature/dakota/data/annotation_ready_financial_evidence.json) (82 Live Telegram Records, Unannotated)  

---

## 1. Executive Summary & Production Recommendation

### Recommendation: **NO-GO FOR MAIN MERGE / NO-GO FOR GLOBAL PRODUCTION ACTIVATION**

The conservative integration of official Featherless AI Simple JEV with Qwen3.5-9B 4-bit NF4 successfully satisfies architectural parity, single-instance singleton VRAM protection, deterministic prompt compilation, token boundary invariants, and evidence provenance. 

However, Phase 3 real financial-data evaluation reveals **two critical blockers** that preclude merging to `main` or enabling JEV globally at this stage:

1. **Absence of Human-Verified Ground-Truth on Real Live Telegram Data**:
   - The repository's operational Telegram captures in `data/live/investigations.jsonl` (82 records, 60 unique fingerprints, 30 with external Google/Yahoo RSS headlines and BSE filings) possess **zero human ground-truth labels**.
   - Per non-negotiable safety constraints *(Rule #8: "Do not invent dataset records, ground-truth labels, or evaluation results"; Rule #9: "If human labels are missing, stop before claiming real-world accuracy and provide an annotation-ready file")*, we have prepared a comprehensive annotation workflow in [`data/annotation_ready_financial_evidence.json`](file:///d:/dakota%20V4%20with%20telegram%20integrated/dakota%20integ.%20d11%20final%20prototype1%20minus%20telegram%20feature/dakota/data/annotation_ready_financial_evidence.json). 
   - Real-world production accuracy **cannot be credibly claimed** on live data until human annotation is completed.

2. **Severe Latency Cliff from Host GUI VRAM Contention and PCIe Paging**:
   - On an 8.00 GiB physical VRAM budget (RTX 4060 Laptop GPU), Windows host applications (Desktop Window Manager, Edge, IDE) consume ~740 MiB before WSL2 starts, leaving ~7.27 GiB of physical VRAM.
   - The 4-bit NF4 model consumes 7.12 GiB of allocated weights. During long-sequence prompts (~1,143 tokens), peak activation memory reaches **7.40 GiB**.
   - This breaches the physical VRAM headroom, causing Windows WDDM to page memory buffers across the PCIe bus into host RAM. 
   - In addition, `causal_conv1d_fn` and `chunk_gated_delta_rule` in the Qwen 3.5 architecture fall back to pure PyTorch reference loops because native compiled CUDA kernels are not installed (per constraint #7, dependencies were not altered).
   - This creates a **latency cliff**: short prompts (~400 tokens) run in ~12.8 seconds, but full financial evidence prompts (~1,143 tokens) require **several minutes per sample**.

### Recommended Action Plan:
- **Maintain JEV behind feature flag**: Keep `DAKOTA_USE_JEV=0` as the default in Project Dakota.
- **Do not merge branch**: Keep integration isolated on `feature/integrate-official-simple-jev`.
- **Execute Human Annotation**: Complete manual labeling using the provided [`data/annotation_ready_financial_evidence.json`](file:///d:/dakota%20V4%20with%20telegram%20integrated/dakota%20integ.%20d11%20final%20prototype1%20minus%20telegram%20feature/dakota/data/annotation_ready_financial_evidence.json).
- **Propose Phase 4 Optimization**: Seek explicit authorization for native compilation of `causal_conv1d` and `flash-linear-attention` or evaluation on a headless Linux host with $\ge 12$ GiB dedicated VRAM.

---

## 2. Evaluation Harness Audit & Bug Fixes (Task 1)

Before conducting the real model evaluation, we audited the evaluation harness and supporting modules:
- [`scripts/evaluate_financial_evidence.py`](file:///d:/dakota%20V4%20with%20telegram%20integrated/dakota%20integ.%20d11%20final%20prototype1%20minus%20telegram%20feature/dakota/scripts/evaluate_financial_evidence.py)
- [`src/intelligence/jev/tasks/sentiment.py`](file:///d:/dakota%20V4%20with%20telegram%20integrated/dakota%20integ.%20d11%20final%20prototype1%20minus%20telegram%20feature/dakota/src/intelligence/jev/tasks/sentiment.py)
- [`src/intelligence/jev/adapters/official_jev_adapter.py`](file:///d:/dakota%20V4%20with%20telegram%20integrated/dakota%20integ.%20d11%20final%20prototype1%20minus%20telegram%20feature/dakota/src/intelligence/jev/adapters/official_jev_adapter.py)
- [`tests/test_official_jev_integration.py`](file:///d:/dakota%20V4%20with%20telegram%20integrated/dakota%20integ.%20d11%20final%20prototype1%20minus%20telegram%20feature/dakota/tests/test_official_jev_integration.py)

### Confirmed Harness Inconsistencies & Minimal Fixes

| Audit Item | Pre-Audit Inconsistency | Resolution & Verification |
| :--- | :--- | :--- |
| **Class Taxonomy** | Only 5 classes defined; `"Ambiguous"` was missing from `candidate_classes` and `STANDARD_CLASSES`. | Added `"Ambiguous"` to `STANDARD_CLASSES` and `SentimentDivergenceTask.candidate_classes`, completing the 6 canonical classes (`Bullish`, `Bearish`, `Neutral`, `Mixed`, `Ambiguous`, `Insufficient Evidence`). |
| **Token BPE Alignment** | Need to ensure candidate label `F` (Insufficient Evidence) satisfies single-token invariant without BPE merge. | Tokenizer check in WSL2 verified: `A=32, B=33, C=34, D=35, E=36, F=37`. All 6 candidates are single tokens following `Answer: (` with zero merge. |
| **Split Isolation (`--held-out`)** | `--held-out` was parsed but ignored when `--dataset` was supplied, risking data leakage. | Implemented strict split filtering in `main()`. Added explicit `"split": "held_out"` tags and `--split {held_out,dev,all}` support. |
| **Abstention Confounding** | `insufficient_evidence_count`, `ambiguous_count`, and `low_confidence_abstentions` were lumped into a single counter. | Separated tracking of: 1) `insufficient_evidence_count`, 2) `ambiguous_count` (margin < 0.05 or ambiguous label), 3) `low_confidence_abstentions` (< 0.40). |
| **Calibration Metrics** | NLL computation had potential $-\infty$ spikes on unpredicted true classes; ECE binning was undocumented. | Added epsilon floor of $10^{-7}$ for NLL. Documented equal-width 10-bin partitioning over $[0.0, 1.0]$. Fixed explicit class ordering parameter. |
| **Balanced Accuracy** | Only overall accuracy and Macro-F1 were computed. | Added `balanced_accuracy` (unweighted average of recalls across supported classes). |
| **VRAM Management** | PyTorch allocator held fragmented blocks from model loading into inference. | Added `torch.cuda.empty_cache()` immediately post-load and before/after each forward pass. |

All fixes were validated with 3 dedicated regression tests in [`tests/test_official_jev_integration.py`](file:///d:/dakota%20V4%20with%20telegram%20integrated/dakota%20integ.%20d11%20final%20prototype1%20minus%20telegram%20feature/dakota/tests/test_official_jev_integration.py) (Tests 14, 15, and 16). All 27 suite tests passed cleanly.

---

## 3. Data Inventory & Provenance (Task 2 & 3)

We performed a comprehensive inventory of all financial datasets, disclosure logs, and intelligence records across the repository:

### Repository Data Inventory

| Dataset Source | Path | Format | Records | Provenance & Labeling Status | Split / Usage |
| :--- | :--- | :---: | :---: | :--- | :--- |
| **Curated Equity Benchmark** | `src/intelligence/jev/dataset.py` | Python / Pydantic | 15 | Handcrafted development benchmark based on real Indian market cases (Reliance, Paytm, Infosys, Suzlon, Zomato, etc.). Hand-annotated with expert rationales. | **Development** (`dev`). Zero overlap with held-out. |
| **Held-Out Equity Benchmark** | `scripts/evaluate_financial_evidence.py` | Python dicts | 7 | Curated held-out benchmark covering 6 classes and 7 linguistic challenges (`HELD-001` to `HELD-007`). Hand-verified ground truth with explicit provenance. | **Held-Out** (`held_out`). Strictly isolated. |
| **Live Ingested Telegram Feeds** | `data/live/investigations.jsonl` | JSONL | 82 | Real-world Indian financial Telegram messages ingested by Dakota. 60 unique fingerprints; 30 records possess external RSS news headlines or BSE filings. **0 human ground-truth labels.** | **Unlabeled Live**. Converted into annotation template. |
| **Tip Captures** | `data/tips/investigations.jsonl` | JSONL | 191 | Raw tip alerts from monitored channels. **0 human ground-truth labels.** | **Unlabeled Live**. |
| **Dakota SQLite Database** | `data/dakota.db` | SQLite | 77 tips, 66 msgs | Operational storage of channel messages and rule classifications. **0 human ground-truth labels.** | **Unlabeled Operational**. |

### Preventing Data Leakage
- **ID Separation**: Development records use prefix `IN-20260915-xxx` to `IN-20261018-xxx`. Held-out records use prefix `HELD-001` to `HELD-007`. Intersection is $\emptyset$.
- **Temporal Separation**: Development events span September 15 to October 18, 2026. Held-out events span distinct corporate announcements and dates.
- **Entity & Event Isolation**: No identical headline or corporate filing appears in both splits.

---

## 4. Human Annotation Workflow for Real Live Data (Task 3)

Per Rule #9, because `data/live/investigations.jsonl` lacks human labels, we extracted all 82 records into an annotation-ready dataset template:
- **File Path**: [`data/annotation_ready_financial_evidence.json`](file:///d:/dakota%20V4%20with%20telegram%20integrated/dakota%20integ.%20d11%20final%20prototype1%20minus%20telegram%20feature/dakota/data/annotation_ready_financial_evidence.json)
- **Record Schema**:
  ```json
  {
    "record_id": "ANN-LIVE-001",
    "ticker": "CRUDE_OIL",
    "original_text": "Source: @markemahakelpredictions | Entity: crudeoil | (Urgent call) | Type: a commodity trading tip",
    "news_headlines": [
      "[r/crudeoil] Crude Oil Trading",
      "[r/oil] Oil, gas, and other products that keep the world flowing",
      "[r/worldnews] World News",
      "[r/mesmnqmorningbrief] DAILY MARKET BRIEF ~ Published Thursday October 8, 2026",
      "[r/indiafinance] Should I fast track or hold the purchase of land worth of around 20 Lakh?"
    ],
    "sources": [
      {"name": "Reddit (r/crudeoil)", "url": "https://www.reddit.com/r/CrudeOil/", "title": "Crude Oil Trading"}
    ],
    "published_at": "2026-10-08T12:20:26+00:00",
    "collected_at": "2026-10-08T12:20:26+00:00",
    "duplicate_group": "b7ab0b4c183948ce",
    "duplicate_count": 1,
    "duplicate_peers": [],
    "human_reviewed_label": null,
    "annotation_rationale": null,
    "evidence_ids": ["E_LIVE_TG_CRUDE_OIL_001", "E_DISC_CRUDE_OIL_001"],
    "sample": { ... }
  }
  ```

### Annotation Instructions for Reviewers:
1. Open [`data/annotation_ready_financial_evidence.json`](file:///d:/dakota%20V4%20with%20telegram%20integrated/dakota%20integ.%20d11%20final%20prototype1%20minus%20telegram%20feature/dakota/data/annotation_ready_financial_evidence.json).
2. For each record, review `original_text`, `news_headlines`, and market `sample` data.
3. In `human_reviewed_label`, enter one of the 6 canonical labels:
   - `"Bullish"`: Clear positive operational beat, institutional accumulation, or verified breakout.
   - `"Bearish"`: Deteriorating fundamentals, regulatory action, or breakdown.
   - `"Neutral"`: Balanced, range-bound, ordinary corporate updates, or normal operations.
   - `"Mixed"`: Clear divergence (e.g. promotional hype vs. low delivery volume or surveillance).
   - `"Ambiguous"`: Contradictory reports of equal credibility or inherently undecidable claims.
   - `"Insufficient Evidence"`: Unsubstantiated claims lacking verifiable market data or filings.
4. Document the rationale in `annotation_rationale`.
5. Once completed, run:
   ```bash
   python scripts/evaluate_financial_evidence.py --dataset data/annotation_ready_financial_evidence.json --adapter official_jev
   ```

---

## 5. Real Model Inference Verification (Task 4.1 Probe)

Before evaluating the full dataset, we executed a single labeled probe sample (`HELD-001`, INFY) in the WSL2 GPU environment to confirm real hardware inference:

### Probe Execution Metadata
- **Command**:
  ```bash
  wsl -e bash -c "cd '/mnt/d/dakota V4 with telegram integrated/dakota integ. d11 final prototype1 minus telegram feature/dakota' && /home/vdish/dakota-jev/.venv/bin/python scratch/run_real_probe.py"
  ```
- **Device**: NVIDIA GeForce RTX 4060 Laptop GPU (8.00 GiB)
- **Model Load Time**: 66.58 seconds
- **Post-Load VRAM Allocated**: 7.12 GiB
- **Post-Load VRAM Reserved**: 7.21 GiB
- **Peak VRAM During Inference**: 7.40 GiB
- **Singleton Guard**: Verified. Second adapter instance reported `is_loaded=True` without reloading weights.

### Probe Results (`HELD-001` — Infosys upward revenue guidance revision)
- **Target Ground Truth**: `Bullish`
- **Model Prediction**: `Bullish` (Exact Match)
- **Uncalibrated Softmax Confidence**: `0.9766`
- **Softmax Margin**: `0.9665`
- **Shannon Entropy**: `0.1382`
- **Evidence Provenance**: Output preserved `['E_MKT_INFY', 'E_NEWS_INFY', 'E_SOC_INFY']`.
- **Prompt Hash**: `62572cda8a742187...`

### Probability Vector & Raw Choice Logits
| Candidate Class | Token ID | Raw Logit | Softmax Probability |
| :--- | :---: | :---: | :---: |
| **Bullish** | 32 (`A`) | **27.0000** | **0.9766** |
| **Bearish** | 33 (`B`) | 22.4219 | 0.0100 |
| **Neutral** | 34 (`C`) | 22.1562 | 0.0077 |
| **Mixed** | 35 (`D`) | 21.7656 | 0.0052 |
| **Ambiguous** | 36 (`E`) | 17.3594 | 0.0001 |
| **Insufficient Evidence** | 37 (`F`) | 19.3125 | 0.0004 |
| **Sum** | — | — | **1.000000** |

All safety and contract invariants were confirmed:
1. Real model inference occurred on the RTX 4060 GPU.
2. The prediction mapped to the correct canonical class.
3. Softmax probabilities summed to exactly 1.0.
4. Softmax confidence was explicitly marked `is_calibrated=False`.
5. Evidence IDs survived the full pipeline without loss.

---

## 6. Evaluation Metrics on Held-Out Benchmark (Task 5)

The held-out evaluation was executed sequentially using the updated harness on the genuine local Qwen3.5-9B 4-bit NF4 model in WSL2 against the 7 curated Indian equity benchmark records (`HELD-001` through `HELD-007`). Results are saved in [`data/held_out_real_evaluation_results.json`](file:///d:/dakota%20V4%20with%20telegram%20integrated/dakota%20integ.%20d11%20final%20prototype1%20minus%20telegram%20feature/dakota/data/held_out_real_evaluation_results.json):

### Summary Statistics
- **Eligible Samples**: 7
- **Evaluated Samples**: 7
- **Skipped / Failed Samples**: 0 / 0
- **Overall Accuracy**: **85.71%** (6 / 7)
- **Balanced Accuracy**: **83.33%**
- **Macro-Precision**: **0.7500**
- **Macro-Recall**: **0.8333**
- **Macro-F1**: **0.7778**
- **Abstention Rate**: 14.29% (1 sample: `HELD-005` explicit Insufficient Evidence)
- **Coverage Rate**: 85.71%
- **Evidence Attribution Rate**: 100.00%
- **Class Ordering**: `['Bullish', 'Bearish', 'Neutral', 'Mixed', 'Ambiguous', 'Insufficient Evidence']`

### Class-Level Breakdown
| Class | Precision | Recall | F1-Score | Support |
| :--- | :---: | :---: | :---: | :---: |
| **Bullish** | 1.0000 | 1.0000 | 1.0000 | 1 |
| **Bearish** | 1.0000 | 1.0000 | 1.0000 | 1 |
| **Neutral** | 1.0000 | 1.0000 | 1.0000 | 2 |
| **Mixed** | 0.5000 | 1.0000 | 0.6667 | 1 |
| **Ambiguous** | 0.0000 | 0.0000 | 0.0000 | 1 |
| **Insufficient Evidence** | 1.0000 | 1.0000 | 1.0000 | 1 |

### Confusion Matrix
| Actual \ Predicted | Bullish | Bearish | Neutral | Mixed | Ambiguous | Insufficient Evidence |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Bullish** | **1** | 0 | 0 | 0 | 0 | 0 |
| **Bearish** | 0 | **1** | 0 | 0 | 0 | 0 |
| **Neutral** | 0 | 0 | **2** | 0 | 0 | 0 |
| **Mixed** | 0 | 0 | 0 | **1** | 0 | 0 |
| **Ambiguous** | 0 | 0 | 0 | **1** | 0 | 0 |
| **Insufficient Evidence** | 0 | 0 | 0 | 0 | 0 | **1** |

### Calibration Performance (Separated from Accuracy)
- **Multi-Class Brier Score**: **0.1889** *(quadratic probability error; lower is better)*
- **Expected Calibration Error (ECE)**: **0.0965** *(equal-width 10-bin gap between confidence and accuracy)*
- **Negative Log-Likelihood (NLL)**: **0.3645** *(with $\epsilon=10^{-7}$ floor)*
- **Calibration Binning Method**: `equal_width_10_bins` over $[0.0, 1.0]$

> [!NOTE]
> **Understanding JEV Calibration Limitations**:  
> Softmax scores derived over a restricted letter set (`A` through `F`) represent **choice probabilities conditioned on the prompt and rubric**, NOT calibrated probabilities of real-world equity price movement. The high confidence (0.97–0.99) reflects strong logit separation at the choice token, but must not be treated as a 97% probability of market profit. Any production use must apply post-hoc calibration (e.g., Platt scaling or temperature scaling).

---

## 7. Linguistic Edge-Case & Error Analysis (Task 6)

We evaluated representative edge cases designed to stress-test financial NLP vulnerabilities:

### 1. Negation and Denials (`HELD-002`, VEDL) — PASSED
- **Context**: Promoter denies default rumors, but bond yields spike. SEBI denies restructuring permission and levies penalty.
- **Vulnerability**: Models often see "denies default rumors" and predict Neutral or Bullish.
- **Model Behavior**: The model correctly classified the record as **Bearish**, attending to the regulatory denial ("SEBI denies permission") and bond yield spike rather than the promoter's verbal denial.

### 2. Conflicting Reports & Social Divergence (`HELD-003`, SUZLON) — PASSED
- **Context**: Aggressive Telegram touting ("JOIN VIP GROUP! Target ₹150 guaranteed 200% return") while BSE files inquiry regarding unusual volume and delivery volume collapses to 18.2%.
- **Vulnerability**: Generative LLMs typically latch onto the promotional hype or classify as Bullish.
- **Model Behavior**: JEV correctly resolved the tension as **Mixed**, adhering to the prompt instruction to prioritize exchange surveillance and delivery collapse over promotional chatter.

### 3. Stale Information Repost (`HELD-006`, TATASTEEL) — PASSED
- **Context**: Social media reposts a month-old UK government grant announcement as "Breaking News", while stock price is flat (+0.10%) and delivery is normal (51.0%).
- **Vulnerability**: News sentiment extractors flag the grant as positive.
- **Model Behavior**: Correctly classified as **Neutral**, recognizing that market indicators are flat and the news is stale.

### 4. Macroeconomic vs. Company-Specific Events (`HELD-004`, HDFCBANK) — PASSED
- **Context**: RBI monetary policy committee holds repo rate unchanged at 6.50% in line with expectations.
- **Model Behavior**: Correctly classified as **Neutral**, distinguishing broad in-line macroeconomic decisions from idiosyncratic bank earnings beats.

### 5. Speculative Touts with No Telemetry (`HELD-005`, UNKNOWN_SHELL) — PASSED
- **Context**: Unverified Telegram spam promising "100% sure-shot scrip" with zero exchange data, no filings, and no price history.
- **Model Behavior**: The pipeline invoked `_check_insufficient_evidence`, returning **Insufficient Evidence** with uniform probabilities and 0 ms latency, preventing ungrounded hallucination.

### 6. Ambiguous / Evenly Divided Analyst Splits (`HELD-007`, WIPRO) — DETAILED ERROR ANALYSIS
- **Context**: Goldman Sachs upgrades Wipro to Buy citing deal win ramp-up; Nomura simultaneously downgrades to Reduce citing margin compression. Stock is flat (+0.02%, delivery 48.0%).
- **Target Label**: `Ambiguous`
- **Model Prediction**: `Mixed`
- **Root Cause Analysis**: 
  - The model identified the prominent conflict between institutional brokers (Goldman Sachs Buy vs. Nomura Reduce).
  - In JEV's rubric, `Mixed` is defined as *"Prominent conflict between sources..."* while `Ambiguous` is defined as *"Available context contains contradictory indicators of comparable strength..."*.
  - Because both definitions emphasize conflict, the model's logits favored `Mixed` (option `D`) over `Ambiguous` (option `E`).
  - **Diagnostic Confirmation**: The model's top margin between `Mixed` and `Ambiguous` was **0.0476** (< 0.05), which successfully triggered Dakota's low-margin ambiguity diagnostic flag (`ambiguous_count = 1`), proving that the ambiguity detector is functioning as intended.

---

## 8. Latency and Hardware Profile (Task 5 & 7)

| Parameter | Measured Value | Operational Assessment |
| :--- | :---: | :--- |
| **Physical GPU** | NVIDIA GeForce RTX 4060 Laptop GPU | 8.00 GiB VRAM limit |
| **Pre-run Host VRAM Consumption** | ~740 MiB | Windows DWM, Edge, Antigravity IDE |
| **Effective Headroom** | ~7.26 GiB | Maximum physical memory before paging |
| **Model Weights (4-bit NF4)** | 7.12 GiB | Residual margin: ~140 MiB |
| **Peak VRAM During Inference** | **7.42 GiB** | Paged slightly across PCIe bus |
| **Mean Latency** | **84.23 s** (84,229 ms) | Across all 7 held-out samples |
| **Median Latency** | **63.15 s** (63,151 ms) | Measured on sequential evaluation |
| **P90 / P95 Latency** | **193.29 s** (193,294 ms) | Occurred on longest context sample (`HELD-007`) |
| **CUDA Kernels** | Reference fallback | `causal_conv1d` and `flash-linear-attention` not compiled |

---

## 9. Limitations & Reproducibility Instructions

### Limitations
1. **Unlabeled Live Feeds**: Real Indian Telegram messages currently lack ground-truth human annotations. Real-world precision on noisy social channels cannot be quantified until annotation is complete.
2. **Hardware Constraints**: The 8 GB VRAM capacity of the RTX 4060 Laptop GPU is at the absolute lower threshold for running a 9B parameter model in 4-bit NF4 under Windows WDDM.
3. **Sequential Processing**: Batching was deliberately avoided in Phase 3 per non-negotiable safety constraints.

### Exact Reproducibility Instructions

#### 1. Unit & Regression Tests (Windows Host)
```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_jev_core.py tests/test_official_jev_integration.py -v
```

#### 2. Verify Single Probe Sample in WSL2
```bash
wsl -e bash -c "cd '/mnt/d/dakota V4 with telegram integrated/dakota integ. d11 final prototype1 minus telegram feature/dakota' && /home/vdish/dakota-jev/.venv/bin/python scratch/run_real_probe.py"
```

#### 3. Run Evaluation Script on Held-Out Split in WSL2
```bash
wsl -e bash -c "cd '/mnt/d/dakota V4 with telegram integrated/dakota integ. d11 final prototype1 minus telegram feature/dakota' && /home/vdish/dakota-jev/.venv/bin/python scripts/evaluate_financial_evidence.py --adapter official_jev --held-out --output data/held_out_real_evaluation_results.json"
```

#### 4. Run Mock Adapter Baseline (Instantaneous)
```powershell
.\.venv\Scripts\python.exe scripts/evaluate_financial_evidence.py --adapter mock --held-out
```

---

## 10. Proposed Acceptance Thresholds for Future Phase 4

Per Task 7 instructions *(Rule: "Do not fabricate acceptance thresholds. If no thresholds have been agreed upon, present the measured results and propose thresholds for review")*, we propose the following acceptance thresholds for stakeholder review prior to any production merge:

| Metric | Measured Baseline (Phase 3 Held-Out) | Proposed Phase 4 Production Threshold | Rationale |
| :--- | :---: | :---: | :--- |
| **Overall Accuracy** | 85.71% | $\ge 82.0\%$ (on annotated live data) | Accommodates extreme noise in live Telegram messages. |
| **Balanced Accuracy** | 83.33% | $\ge 78.0\%$ | Prevents majority-class bias on imbalanced feeds. |
| **Macro-F1** | 0.7778 | $\ge 0.7500$ | Ensures minority classes (e.g. Mixed, Ambiguous) perform well. |
| **Abstention Accuracy**| 100.0% (`HELD-005`) | $\ge 90.0\%$ | Must never predict Bullish on ungrounded spam touts. |
| **Multi-Class Brier** | 0.1889 | $\le 0.1800$ | Well-calibrated probabilities. |
| **Expected Calibration (ECE)**| 0.0965 | $\le 0.1200$ | Ensures confidence tracks empirical precision. |
| **Inference Latency (P90)** | 193.29 s (reference PyTorch) | $\le 5.0$ s (with compiled kernels / dedicated GPU) | Required for interactive investigation workflows. |
| **VRAM Headroom** | 0.14 GiB (insufficient) | $\ge 2.0$ GiB headroom | Eliminates PCIe paging thrashing. |

---

## 11. Conclusion

Project Dakota Phase 3 establishes a rigorous, transparent evaluation foundation for JEV classification. 

The architecture is mathematically sound, preserves evidence provenance, and correctly handles complex financial linguistic phenomena (negation, conflicting reports, stale news, and speculation). However, **production deployment must remain blocked (NO-GO)** until:
1. The 82 live Telegram records are manually labeled using the provided template ([`data/annotation_ready_financial_evidence.json`](file:///d:/dakota%20V4%20with%20telegram%20integrated/dakota%20integ.%20d11%20final%20prototype1%20minus%20telegram%20feature/dakota/data/annotation_ready_financial_evidence.json)).
2. Inference latency is resolved via native CUDA kernels or deployment on a dedicated headless GPU environment.
