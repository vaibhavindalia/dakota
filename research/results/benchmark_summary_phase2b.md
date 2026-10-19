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
| **JEV (Qwen/Qwen3.5-9B)** | 77.78% | 0.6933 | 0.3729 | 0.2036 | 0.8294 | 22179.2 ms | 0 |
| **Qwen Generative (Qwen/Qwen3.5-9B)** | 11.11% | 0.0400 | 1.2236 | 0.5889 | 2.3421 | 5881.9 ms | 30 |

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
- **Mean Latency**: 0.53 ms (p95: 0.69 ms)
- **Tokens Generated**: 0.0

### JEV (Qwen/Qwen3.5-9B)
- **Accuracy**: 77.78%
- **Macro-F1**: 0.6933
- **Brier Score**: 0.3729
- **ECE**: 0.2036
- **Negative Log-Likelihood**: 0.8294
- **Mean Latency**: 22179.22 ms (p95: 23366.08 ms)
- **Tokens Generated**: 0.0

### Qwen Generative (Qwen/Qwen3.5-9B)
- **Accuracy**: 11.11%
- **Macro-F1**: 0.0400
- **Brier Score**: 1.2236
- **ECE**: 0.5889
- **Negative Log-Likelihood**: 2.3421
- **Mean Latency**: 5881.92 ms (p95: 8030.27 ms)
- **Tokens Generated**: 30.0

