# Dakota StockTwits DDGS switch v2

Replaces `src/evidence/stocktwits.py` with a free DDGS/public-search adapter.

The v2 result semantics are cleaned up:
- `status=connected` when usable StockTwits results were found.
- `error=null` when usable results exist.
- `warnings` contains soft search-provider misses from secondary queries.
- This is public search discovery, not a complete StockTwits feed.
