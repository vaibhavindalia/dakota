import urllib.parse
import json
import feedparser
import os
try:
    from google import genai
except ImportError:
    genai = None

from typing import Any, Dict, List


# Pulkit's original implementation uses the Yahoo Finance RSS feed, but Yahoo
# expects Indian NSE symbols in the form CDSL.NS rather than plain CDSL.
# Dakota keeps its internal ticker as CDSL and translates it only at the
# provider boundary.
def _normalize_yahoo_symbol(ticker: str) -> str:
    value = (ticker or "").strip().upper()
    if not value:
        return ""

    # Accept common Indian suffix forms while keeping Dakota's internal ticker
    # convention unchanged.
    if value.endswith(".NSE"):
        value = value[:-4]
    elif value.endswith(".BSE"):
        value = value[:-4]

    if value.endswith(".NS"):
        return value

    return f"{value}.NS"


def fetch_yahoo_news(ticker: str, max_items: int = 5) -> List[Dict[str, Any]]:
    """Fetch recent Yahoo Finance RSS news for an Indian NSE ticker."""
    yahoo_symbol = _normalize_yahoo_symbol(ticker)
    safe_ticker = urllib.parse.quote_plus(yahoo_symbol)
    rss_url = (
        "https://feeds.finance.yahoo.com/rss/2.0/headline"
        f"?s={safe_ticker}&region=IN&lang=en-IN"
    )

    try:
        feed = feedparser.parse(rss_url)
        news_items: List[Dict[str, Any]] = []

        for entry in feed.entries[:max_items]:
            news_items.append(
                {
                    "headline": entry.get("title", ""),
                    "link": entry.get("link", ""),
                    "published_at": entry.get("published", ""),
                    "source": entry.get("publisher", "Yahoo Finance"),
                    "provider": "Yahoo Finance RSS",
                    "provider_symbol": yahoo_symbol,
                }
            )

        return news_items
    except Exception:
        return []


def fetch_google_news(ticker: str, max_items: int = 5) -> List[Dict[str, Any]]:
    """Fetch recent news for a ticker from Google News RSS."""
    safe_ticker = urllib.parse.quote_plus(f"{ticker} stock NSE BSE")
    rss_url = (
        "https://news.google.com/rss/search?"
        f"q={safe_ticker}&hl=en-IN&gl=IN&ceid=IN:en"
    )

    try:
        feed = feedparser.parse(rss_url)
        news_items: List[Dict[str, Any]] = []

        for entry in feed.entries[:max_items]:
            source = entry.get("source") or {}
            news_items.append(
                {
                    "headline": entry.get("title", ""),
                    "link": entry.get("link", ""),
                    "published_at": entry.get("published", ""),
                    "source": (
                        source.get("title", "Google News")
                        if isinstance(source, dict)
                        else "Google News"
                    ),
                    "provider": "Google News RSS",
                }
            )

        return news_items
    except Exception:
        return []


def analyze_news_with_llm(
    ticker: str,
    news_items: List[Dict[str, Any]],
    tip_context: str = "",
) -> Dict[str, Any]:
    """
    Analyze collected headlines with Groq first and Gemini second.

    The returned risk_score_modifier is preserved for compatibility with
    Pulkit's original module. Dakota's production risk engine should treat this
    as evidence/context rather than allowing an LLM to directly set the final
    Dakota risk score.
    """
    if not news_items:
        return {
            "is_credible_reason": False,
            "explanation": "No recent news found to justify the movement.",
            "risk_score_modifier": 0,
        }

    headlines = "\n".join(
        f"- {item['headline']} (Source: {item['source']})"
        for item in news_items
    )

    prompt = f"""
    A stock tip was given for {ticker}. Context: {tip_context}
    Here are the recent news headlines for {ticker}:
    {headlines}

    Based on these headlines, is there a credible fundamental reason (like an order win, earnings growth, merger)
    for the stock to experience a sudden pump? Or is it likely fake hype?
    Respond strictly in JSON format.
    Schema: {{"is_credible_reason": bool, "explanation": "string", "risk_score_modifier": integer}}
    Note: risk_score_modifier should be between -20 and 0. Use 0 if no credible reason, e.g. -15 if strong positive news.
    """

    import time

    groq_api_key = os.getenv("GROQ_API_KEY")
    if groq_api_key:
        try:
            from groq import Groq

            client = Groq(api_key=groq_api_key)
            chat_completion = client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a financial analyst AI. Output strictly valid JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
                model="qwen/qwen3.8-27b",
                response_format={"type": "json_object"},
                temperature=0.2,
            )
            result_json = json.loads(chat_completion.choices[0].message.content)
            result_json["explanation"] = (
                "[Powered by Groq 🚀] " + result_json.get("explanation", "")
            )
            return result_json
        except Exception as exc:
            print(f"Groq API failed, falling back to Gemini... Error: {exc}")

    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if gemini_api_key and genai:
        try:
            client = genai.Client(api_key=gemini_api_key)
            max_retries = 2

            for attempt in range(max_retries):
                try:
                    response = client.models.generate_content(
                        model="gemini-3.8-flash",
                        contents=prompt,
                        config=genai.types.GenerateContentConfig(
                            response_mime_type="application/json"
                        ),
                    )
                    result_json = json.loads(response.text)
                    result_json["explanation"] = (
                        "[Powered by Gemini Fallback] "
                        + result_json.get("explanation", "")
                    )
                    return result_json
                except Exception as exc:
                    if "503" in str(exc) and attempt < max_retries - 1:
                        time.sleep(1)
                        continue
                    raise

        except Exception as exc:
            return {
                "is_credible_reason": False,
                "explanation": (
                    f"[Error] Both APIs failed. Gemini Error: {str(exc)}"
                ),
                "risk_score_modifier": 0,
            }

    has_good_news = any(
        word in headlines.lower()
        for word in ["profit", "win", "acquires", "surge", "contract", "revenue"]
    )

    return {
        "is_credible_reason": has_good_news,
        "explanation": (
            "[Mock LLM - Missing API Keys] "
            + (
                "Found positive corporate news."
                if has_good_news
                else "No solid news found."
            )
        ),
        "risk_score_modifier": -15 if has_good_news else 0,
    }


def verify_news_for_ticker(
    ticker: str,
    tip_context: str = "",
) -> Dict[str, Any]:
    """Fetch Yahoo + Google News and optionally analyze the results."""
    try:
        yahoo_news = fetch_yahoo_news(ticker, max_items=5)
        google_news = fetch_google_news(ticker, max_items=5)

        seen_links = set()
        news_items: List[Dict[str, Any]] = []

        for item in yahoo_news + google_news:
            link = item.get("link", "")
            key = link or item.get("headline", "")
            if key in seen_links:
                continue
            seen_links.add(key)
            news_items.append(item)

        llm_analysis = analyze_news_with_llm(
            ticker,
            news_items,
            tip_context,
        )

        return {
            "ticker": ticker,
            "status": "success",
            "has_recent_news": bool(news_items),
            "provider_status": {
                "yahoo": "connected" if yahoo_news else "no_results",
                "google": "connected" if google_news else "no_results",
            },
            "yahoo_count": len(yahoo_news),
            "google_count": len(google_news),
            "news_events": news_items,
            "llm_analysis": llm_analysis,
        }
    except Exception as exc:
        return {
            "ticker": ticker,
            "status": "error",
            "error_message": str(exc),
        }


if __name__ == "__main__":
    import sys

    ticker = sys.argv[1] if len(sys.argv) > 1 else "CDSL"
    print(
        json.dumps(
            verify_news_for_ticker(ticker),
            indent=2,
            ensure_ascii=False,
        )
    )
