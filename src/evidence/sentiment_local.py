import logging
from typing import List, Dict, Any

try:
    from transformers import pipeline
    # Load the financial sentiment model locally (ProsusAI/finbert is the industry standard)
    # The model will be downloaded automatically the first time this runs.
    sentiment_pipeline = pipeline("sentiment-analysis", model="ProsusAI/finbert")
except ImportError:
    sentiment_pipeline = None
    logging.warning("Transformers library not found. Using mock/fallback sentiment analysis.")
except Exception as e:
    sentiment_pipeline = None
    logging.warning(f"Error loading FinBERT: {e}")

def analyze_bulk_sentiment(texts: List[str]) -> Dict[str, Any]:
    """
    Analyzes an array of text strings using the local FinBERT NLP model.
    This runs completely offline and costs $0.
    """
    if not texts:
        return {"positive": 0, "negative": 0, "neutral": 0, "total": 0}
        
    if sentiment_pipeline:
        try:
            # FinBERT can handle max 512 tokens, we truncate texts to be safe
            truncated_texts = [str(t)[:500] for t in texts]
            results = sentiment_pipeline(truncated_texts)
            
            counts = {"positive": 0, "negative": 0, "neutral": 0, "total": len(texts)}
            for r in results:
                label = r['label'].lower() # usually 'positive', 'negative', 'neutral'
                if label in counts:
                    counts[label] += 1
            return counts
        except Exception as e:
            logging.error(f"Error during FinBERT analysis: {e}")
            
    # Mock fallback if model fails to load or transformers isn't installed
    counts = {"positive": 0, "negative": 0, "neutral": 0, "total": len(texts)}
    for t in texts:
        text_lower = str(t).lower()
        if any(w in text_lower for w in ["buy", "bull", "moon", "good", "win", "profit", "multibagger"]):
            counts["positive"] += 1
        elif any(w in text_lower for w in ["sell", "bear", "fraud", "bad", "loss", "dump", "operator"]):
            counts["negative"] += 1
        else:
            counts["neutral"] += 1
            
    return counts
