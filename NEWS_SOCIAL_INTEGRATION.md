# Dakota News + Social Integration

This integration keeps Dakota as the master architecture and adds the teammate's working intelligence layer.

## Added
- Yahoo Finance RSS + Google News RSS through `src/evidence/news_analyzer.py`
- FinBERT local sentiment through `src/evidence/sentiment_local.py`
- StockTwits adapter through `src/evidence/stocktwits.py`
- merged `src/evidence/news.py` and `src/evidence/social.py`

## Preserved
- Dakota GDELT news evidence
- Dakota official Reddit connector
- Dakota official X connector
- Dakota Instagram connector
- Dakota existing risk engine
- Dakota investigation and backend pipeline

## Important
The teammate LLM `risk_score_modifier` is retained as explanatory evidence only. It does not directly change Dakota's final risk score. FinBERT sentiment is also evidence metadata, not a direct manipulation verdict.

Do not copy the teammate `.env` or any API keys into the repository.
