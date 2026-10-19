# Project Dakota: JEV + Qwen Empirical Benchmark Results

- **Dataset Size**: 15 samples
- **Walk-Forward Splits**: 2 folds
- **Embargo Purge Window**: 24.0 hours
- **Candidate Classes**: Bullish, Bearish, Neutral, Mixed, Insufficient Evidence

## Comparative Performance

| Model | Accuracy | Macro-F1 | Brier Score | ECE | NLL | Mean Latency (ms) | Tokens Generated |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Majority Baseline** | 22.22% | 0.0727 | 0.8088 | 0.0471 | 1.6330 | 0.0 ms | 0 |
| **TF-IDF + LogReg** | 33.33% | 0.2571 | 0.7820 | 0.1007 | 1.5653 | 0.5 ms | 0 |
| **JEV (Qwen/Qwen2.5-7B-Instruct (JEV v1.0))** | 33.33% | 0.1000 | 0.8040 | 0.0732 | 1.6669 | 5.5 ms | 0 |
| **Frontier Reference (GPT-4o)** | 66.67% | 0.6600 | 0.6190 | 0.3411 | 1.4266 | 580.8 ms | 15 |

## Per-Model Details

### Majority Baseline
- **Accuracy**: 22.22%
- **Macro-F1**: 0.0727
- **Brier Score**: 0.8088
- **ECE**: 0.0471
- **Negative Log-Likelihood**: 1.6330
- **Mean Latency**: 0.00 ms (p95: 0.00 ms)
- **Tokens Generated**: 0.0

### TF-IDF + LogReg
- **Accuracy**: 33.33%
- **Macro-F1**: 0.2571
- **Brier Score**: 0.7820
- **ECE**: 0.1007
- **Negative Log-Likelihood**: 1.5653
- **Mean Latency**: 0.49 ms (p95: 0.61 ms)
- **Tokens Generated**: 0.0

### JEV (Qwen/Qwen2.5-7B-Instruct (JEV v1.0))
- **Accuracy**: 33.33%
- **Macro-F1**: 0.1000
- **Brier Score**: 0.8040
- **ECE**: 0.0732
- **Negative Log-Likelihood**: 1.6669
- **Mean Latency**: 5.51 ms (p95: 5.71 ms)
- **Tokens Generated**: 0.0

### Frontier Reference (GPT-4o)
- **Accuracy**: 66.67%
- **Macro-F1**: 0.6600
- **Brier Score**: 0.6190
- **ECE**: 0.3411
- **Negative Log-Likelihood**: 1.4266
- **Mean Latency**: 580.78 ms (p95: 721.80 ms)
- **Tokens Generated**: 15.0

