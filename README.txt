Complete replacement for src/investigation/universal_investigator.py.

Fix:
- preserves the existing stock investigation evidence tree, especially social
  providers and sentiment
- promotes nested investigation evidence to top-level when needed by the
  frontend
- adds Pulkit Yahoo Finance + Google News News evidence without replacing
  Reddit/X/Instagram/StockTwits/Telegram evidence
- keeps Dakota's existing risk engine as the numeric score authority
