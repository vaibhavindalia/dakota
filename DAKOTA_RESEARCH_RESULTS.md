# DAKOTA — EMPIRICAL RESEARCH BASELINE RESULTS
**Date**: 2026-10-19 14:29:55 UTC  
**Dataset**: `data/research/pre_annotated_financial_evidence.json` (82 evaluated records)  
**Target Label Field**: `ai_suggested_label`  
**Reproducibility Manifest**: `data/research/experiment_manifest.json`  

---

## 1. Baseline Performance Summary

| Model / Baseline | Accuracy | 95% Confidence Interval | Macro F1 | Macro Precision | Macro Recall | Mean Latency | Hardware / Backend |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Majority-Class Baseline** | **64.6%** | [53.8%, 74.1%] | 0.1963 | 0.1616 | 0.2500 | 0.0 ms | CPU (Local .venv) |
| **TF-IDF + Logistic Regression** | **87.8%** | [79.0%, 93.2%] | 0.6373 | 0.6718 | 0.6154 | 0.1 ms | CPU (Local .venv) |
| **TF-IDF + Complement Naive Bayes** | **92.7%** | [84.9%, 96.6%] | 0.6746 | 0.6620 | 0.6923 | 0.1 ms | CPU (Local .venv) |
| **Mock Control (Fixed Logits)** | **3.7%** | [1.2%, 10.2%] | 0.0176 | 0.0091 | 0.2500 | 5.7 ms | CPU Control (Local .venv) |
| **Official Simple JEV (Qwen3.5-9B 4-bit)** | **50.0%** *(2-sample probe)* | [9.5%, 90.5%] | 0.3333 | 0.3333 | 0.5000 | 38,936.9 ms | WSL2 (NVIDIA RTX 4060 8GB VRAM) |

---

## 2. Per-Class Performance Breakdown

### TF-IDF + Logistic Regression
| Class | Precision | Recall | F1-Score | Support |
| :--- | :---: | :---: | :---: | :---: |
| **Bullish** | 0.0000 | 0.0000 | 0.0000 | 3 |
| **Bearish** | 0.0000 | 0.0000 | 0.0000 | 0 |
| **Neutral** | 0.8182 | 0.6923 | 0.7500 | 13 |
| **Mixed** | 1.0000 | 0.7692 | 0.8696 | 13 |
| **Ambiguous** | 0.0000 | 0.0000 | 0.0000 | 0 |
| **Insufficient Evidence** | 0.8689 | 1.0000 | 0.9298 | 53 |

### Confusion Matrix (TF-IDF + Logistic Regression)
| Actual \ Predicted | Bullish | Bearish | Neutral | Mixed | Ambiguous | Insufficient Evidence |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Bullish** | 0 | 0 | 1 | 0 | 0 | 2 |
| **Bearish** | 0 | 0 | 0 | 0 | 0 | 0 |
| **Neutral** | 0 | 0 | 9 | 0 | 0 | 4 |
| **Mixed** | 0 | 0 | 1 | 10 | 0 | 2 |
| **Ambiguous** | 0 | 0 | 0 | 0 | 0 | 0 |
| **Insufficient Evidence** | 0 | 0 | 0 | 0 | 0 | 53 |

---

## 3. Scientific Observations and Defensible Claims

1. **Majority-Class Dominance**: Due to the high prevalence of uncorroborated Telegram claims, `Insufficient Evidence` constitutes 64.6% of the dataset. Any naive model predicting only `Insufficient Evidence` achieves 64.6% accuracy, but has a Macro F1 of only ~0.13.
2. **Classical Text Baselines**: TF-IDF with Logistic Regression captures vocabulary differences between news articles (earnings, rally, penalty) and spam signals, achieving superior Macro F1 over the majority class.
3. **Mock Baseline As Expected Fail-Safe**: Dakota's mock control predicts Bullish heavily, leading to severe penalties on this realistic evidence distribution (low accuracy), proving that the mock baseline functions as a control rather than a real classifier.
4. **Statistical Uncertainty**: With an evaluation sample of 82 records, the 95% Wilson confidence intervals span approximately ±10%. Generalization claims to the entire Indian market cannot be defended from this convenience sample.