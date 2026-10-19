# DAKOTA — 82-RECORD FINANCIAL EVIDENCE AUDIT & PROVENANCE REPORT

**Audit Date**: 2026-10-19 14:21:20 UTC  
**Target Dataset**: `data/annotation_ready_financial_evidence.json` (Synced with `data/annotation_worklist.csv`)  
**Auditor**: Dakota Research & Reliability Engineering Pipeline  
**Dataset Scope**: 82 Live Indian Financial Intelligence & Social Evidence Records (`ANN-LIVE-001` through `ANN-LIVE-082`)

---

## 1. Executive Summary

This audit establishes a defensible, machine-readable inventory of all 82 records currently stored in Dakota's financial evidence dataset. Every record has been verified, cross-checked between JSON and CSV representations, enriched with corroboration status, and partitioned into group-aware leakage-safe splits.

| Metric | Measured Value | Audit Status |
| :--- | :--- | :--- |
| **Total Records** | **82** (Strict sequential `ANN-LIVE-001` to `ANN-LIVE-082`) | **VERIFIED (0 Gaps, 0 Dupes)** |
| **JSON vs CSV Parity** | 82 in JSON, 82 in CSV (0 mismatched IDs) | **PERFECT PARITY** |
| **Unique Duplicate Groups** | **60** (46 Singletons, 14 Multi-Record Clusters) | **VERIFIED** |
| **Records in Duplicate Clusters** | **36 records** (Clusters size 2 to 4) | **MUST PRESERVE ACROSS SPLITS** |
| **Human Ground Truth (Reviewed)** | **1 record** (`ANN-LIVE-001` labeled `Insufficient Evidence` by `REV-VAIBHAV`) | **100% UNTAINTED** |
| **Pending Human Review** | **81 records** (Unreviewed labels strictly preserved as empty) | **PENDING EXCEPTION REVIEW** |
| **Records with External Sourcing** | **30 records** (10 sources: 27, 9 sources: 1, 5 sources: 2) | **PARTIALLY CORROBORATED** |
| **Records without External Sourcing** | **52 records** (Isolated Telegram promotional messages) | **UNSUBSTANTIATED SPAM/CLAIMS** |
| **Non-Financial Messages** | **25 records** (Telegram chat messages with zero market relevance) | **NEGATIVE CONTROL SAMPLES** |

---

## 2. Rigorous Data Provenance & Ingestion Origins

To maintain academic and research defensibility, data origin is strictly separated into verified empirical facts versus inferred mechanisms:

### A. Confirmed Repository Facts
1. **Intake Source File**: All 82 records originate from `data/live/investigations.jsonl` captured on **October 8, 2026** during live Telegram channel monitoring.
2. **Channel Origins**: 
   - `@markemahakelpredictions`: 63 records (76.8%) — specific stock tips, index targets, urgent calls.
   - `@Growx_intraday_groww`: 9 records (11.0%) — intraday alerts.
   - `@minish_fast`: 2 records (2.4%) — non-financial announcements.
   - Public/Private Telegram: 8 records across `@Mystocksin`, `@ScamAlert`, `@FundamentalInvesting`, `@TechnicalChart`, `@testchannel`, `@NIFTY50STOCKSSEBI`.
3. **External Evidence Links**: 
   - 289 external source references across 105 unique URLs.
   - Reddit discussions (`www.reddit.com`): 114 instances across macro subreddits (`r/oil`, `r/indiafinance`, `r/CrudeOil`).
   - Google News syndication (`news.google.com`): 40 instances.
   - Official BSE Announcements: Attached in corporate company investigations.

### B. Inferred Repository Mechanisms
1. **Intake Classification**: Ingested messages were classified by an early local regex/classifier into `message_type` categories. Messages identified as having `status: "classified_non_financial"` had investigations aborted with rationale `"The message is not market-relevant, so no market investigation is opened."`
2. **Text Construction**: The builder script (`scratch/build_annotation_dataset.py`) concatenated structured fields (`Source: ... | Entity: ... | Target: ₹... | Type: ...`) rather than preserving multi-paragraph raw text bodies.

### C. Unknown / Missing Provenance
1. **Market Representativeness**: This dataset is **NOT** a representative random sample of the Indian equity market (NSE/BSE). It is a **convenience sample** of unverified promotional Telegram messages and high-risk social calls captured during a single intake window.
2. **SEBI Regulatory Ground Truth**: Records lack formal SEBI enforcement verification unless mentioned in GDELT/Google News headlines.

---

## 3. Class and Record Categorization

| Category | Record Count | Percentage | Research Utility |
| :--- | :---: | :---: | :--- |
| **Non-Financial Control Messages** | 25 | 30.5% | Negative filtering test; evaluate model abstention. |
| **Uncorroborated Promotional Tips** | 27 | 32.9% | Pure social tips without external evidence; canonical class: `Insufficient Evidence`. |
| **Corroborated Equity Events** | 28 | 34.1% | Real tickers (TCS, CDSL, Zomato, Suzlon, etc.) with attached news/telemetry. |
| **Macro / Commodity Tips** | 2 | 2.4% | Crude oil and index calls. |

---

## 4. Duplicate Group Integrity

- **Total Clusters**: 60 unique clusters.
- **Top Clusters by Membership**:
  - Cluster `a1a595ae50fbf948` (4 records): `ANN-LIVE-002`, `ANN-LIVE-008`, `ANN-LIVE-046`, `ANN-LIVE-051` (CDSL tip).
  - Cluster `f485aa5f82291e0a` (4 records): `ANN-LIVE-014`, `ANN-LIVE-034`, `ANN-LIVE-065`, `ANN-LIVE-066` (TCS tip).
  - Cluster `4c478a834e06fa53` (4 records): `ANN-LIVE-020`, `ANN-LIVE-039`, `ANN-LIVE-040`, `ANN-LIVE-067` (ZOMATO tip).
  - Cluster `00913a48e713589b` (4 records): `ANN-LIVE-058`, `ANN-LIVE-062`, `ANN-LIVE-068`, `ANN-LIVE-080` (IRCTC tip).
- **Leakage Prevention**: All peer records within a cluster are strictly bound to either the Dev split or the Held-Out split. No cluster crosses the split boundary.

---

## 5. Audit Deliverables Generated

1. `data/research/dataset_inventory.json`: Complete machine-readable metadata for all 82 records.
2. `data/research/dataset_inventory.csv`: Tabular inventory for spreadsheet analysis.
3. `data/research/enriched_evidence.json`: Corroboration and source domain synthesis.
4. `data/research/pre_annotated_financial_evidence.json`: AI suggestions strictly isolated from human labels.
5. `data/research/annotation_review_queue.csv`: Prioritized exception review queue for human experts.
6. `data/research/splits_manifest.json`: Group-aware Dev/Held-out split partition.
