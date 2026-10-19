# Project Dakota: JEV + Qwen Empirical Benchmark Results (PHASE2C)

- **Dataset Size**: 15 samples across Indian equity events
- **Walk-Forward Splits**: 2 chronological folds
- **Embargo Purge Window**: 24.0 hours
- **Candidate Classes**: Bullish, Bearish, Neutral, Mixed, Insufficient Evidence
- **Peak VRAM**: Allocated: 7742.1 MiB | Reserved: 8178.0 MiB

## Comparative Performance

| Model | Accuracy | Macro-F1 | Brier Score | ECE | NLL | Mean Latency (ms) | Tokens Generated |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Majority Baseline** | 22.22% | 0.0727 | 0.8088 | 0.0471 | 1.6330 | 0.0 ms | 0 |
| **TF-IDF + LogReg** | 33.33% | 0.2571 | 0.7820 | 0.1007 | 1.5653 | 0.5 ms | 0 |
| **JEV (Qwen/Qwen3.5-9B)** | 77.78% | 0.6933 | 0.3552 | 0.0617 | 0.8218 | 21966.6 ms | 0 |
| **Qwen Generative (Fair Direct, Thinking-Off)** | 66.67% | 0.5533 | 0.5292 | 0.0333 | 1.1012 | 3108.4 ms | 4 |
| **Qwen Generative (Constrained 30-tok Diagnostic)** | 0.00% | 0.0000 | 0.8000 | 0.2000 | 1.6094 | 5916.4 ms | 30 |

> **Statistical Limitation Note**: The evaluation set contains 15 events with 9 walk-forward test predictions. Differences in ECE, Brier score, and accuracy on this sample size cannot establish statistical significance or broad generalization.

## Per-Model Diagnostic Details

### Majority Baseline

- **Accuracy**: 22.22%
- **Macro-F1**: 0.0727 (Weighted-F1: 0.0808)
- **Brier Score**: 0.8088
- **ECE**: 0.0471
- **Negative Log-Likelihood**: 1.6330
- **Mean Latency**: 0.00 ms (p95: 0.00 ms)
- **Tokens Generated**: 0.0

#### Per-Class Metrics

| Class | Precision | Recall | F1 | Support |
| :--- | :---: | :---: | :---: | :---: |
| Bullish | 0.2222 | 1.0000 | 0.3636 | 2 |
| Bearish | 0.0000 | 0.0000 | 0.0000 | 1 |
| Neutral | 0.0000 | 0.0000 | 0.0000 | 2 |
| Mixed | 0.0000 | 0.0000 | 0.0000 | 3 |
| Insufficient Evidence | 0.0000 | 0.0000 | 0.0000 | 1 |

### TF-IDF + LogReg

- **Accuracy**: 33.33%
- **Macro-F1**: 0.2571 (Weighted-F1: 0.3175)
- **Brier Score**: 0.7820
- **ECE**: 0.1007
- **Negative Log-Likelihood**: 1.5653
- **Mean Latency**: 0.51 ms (p95: 0.68 ms)
- **Tokens Generated**: 0.0

#### Per-Class Metrics

| Class | Precision | Recall | F1 | Support |
| :--- | :---: | :---: | :---: | :---: |
| Bullish | 0.2500 | 0.5000 | 0.3333 | 2 |
| Bearish | 0.0000 | 0.0000 | 0.0000 | 1 |
| Neutral | 1.0000 | 0.5000 | 0.6667 | 2 |
| Mixed | 0.2500 | 0.3333 | 0.2857 | 3 |
| Insufficient Evidence | 0.0000 | 0.0000 | 0.0000 | 1 |

### JEV (Qwen/Qwen3.5-9B)

- **Accuracy**: 77.78%
- **Macro-F1**: 0.6933 (Weighted-F1: 0.7333)
- **Brier Score**: 0.3552
- **ECE**: 0.0617
- **Negative Log-Likelihood**: 0.8218
- **Mean Latency**: 21966.64 ms (p95: 22150.70 ms)
- **Tokens Generated**: 0.0

#### Per-Class Metrics

| Class | Precision | Recall | F1 | Support |
| :--- | :---: | :---: | :---: | :---: |
| Bullish | 1.0000 | 1.0000 | 1.0000 | 2 |
| Bearish | 1.0000 | 1.0000 | 1.0000 | 1 |
| Neutral | 0.6667 | 1.0000 | 0.8000 | 2 |
| Mixed | 0.6667 | 0.6667 | 0.6667 | 3 |
| Insufficient Evidence | 0.0000 | 0.0000 | 0.0000 | 1 |

### Qwen Generative (Fair Direct, Thinking-Off)

- **Accuracy**: 66.67%
- **Macro-F1**: 0.5533 (Weighted-F1: 0.5963)
- **Brier Score**: 0.5292
- **ECE**: 0.0333
- **Negative Log-Likelihood**: 1.1012
- **Mean Latency**: 3108.36 ms (p95: 5448.91 ms)
- **Tokens Generated**: 4.9

#### Per-Class Metrics

| Class | Precision | Recall | F1 | Support |
| :--- | :---: | :---: | :---: | :---: |
| Bullish | 0.6667 | 1.0000 | 0.8000 | 2 |
| Bearish | 0.5000 | 1.0000 | 0.6667 | 1 |
| Neutral | 0.6667 | 1.0000 | 0.8000 | 2 |
| Mixed | 1.0000 | 0.3333 | 0.5000 | 3 |
| Insufficient Evidence | 0.0000 | 0.0000 | 0.0000 | 1 |

### Qwen Generative (Constrained 30-tok Diagnostic)

- **Accuracy**: 0.00%
- **Macro-F1**: 0.0000 (Weighted-F1: 0.0000)
- **Brier Score**: 0.8000
- **ECE**: 0.2000
- **Negative Log-Likelihood**: 1.6094
- **Mean Latency**: 5916.41 ms (p95: 8184.20 ms)
- **Tokens Generated**: 30.0

#### Per-Class Metrics

| Class | Precision | Recall | F1 | Support |
| :--- | :---: | :---: | :---: | :---: |
| Bullish | 0.0000 | 0.0000 | 0.0000 | 2 |
| Bearish | 0.0000 | 0.0000 | 0.0000 | 1 |
| Neutral | 0.0000 | 0.0000 | 0.0000 | 2 |
| Mixed | 0.0000 | 0.0000 | 0.0000 | 3 |
| Insufficient Evidence | 0.0000 | 0.0000 | 0.0000 | 1 |

