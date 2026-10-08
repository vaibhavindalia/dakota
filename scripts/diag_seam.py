"""Dakota seam diagnostic — prints real signatures and real return values."""

from __future__ import annotations

import inspect
import json
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intake import tip_intake, live_store
from src.classification import local_classifier as lc
from src.investigation import impact_mapper as mp
from src.investigation import universal_investigator as ui
from src.engine import risk_engine as re_


def show(obj):
    if obj is None:
        return "None"
    if is_dataclass(obj):
        return f"dataclass {type(obj).__name__} -> {json.dumps(asdict(obj), default=str)}"
    if isinstance(obj, dict):
        return f"dict -> {json.dumps(obj, default=str)}"
    if hasattr(obj, "__dict__"):
        inner = {k: v for k, v in vars(obj).items() if not k.startswith('_')}
        return f"object {type(obj).__name__} -> {json.dumps(inner, default=str)}"
    return f"{type(obj).__name__} -> {obj!r}"


print("=" * 70)
print("SIGNATURES")
print("=" * 70)
for label, fn in [
    ("intake_tip", getattr(tip_intake, "intake_tip", None)),
    ("save_live_investigation", getattr(live_store, "save_live_investigation", None)),
    ("load_live_investigations", getattr(live_store, "load_live_investigations", None)),
    ("get_live_investigation", getattr(live_store, "get_live_investigation", None)),
    ("classify_message", getattr(lc, "classify_message", None)),
    ("map_impact", getattr(mp, "map_impact", None)),
    ("investigate_message", getattr(ui, "investigate_message", None)),
    ("investigate_tip", getattr(ui, "investigate_tip", None)),
    ("assess", getattr(re_, "assess", None)),
]:
    if fn is None:
        print(f"{label:28} MISSING")
        continue
    try:
        print(f"{label:28} {inspect.signature(fn)}")
    except (TypeError, ValueError) as exc:
        print(f"{label:28} <unavailable: {exc}>")

TEXTS = [
    "CDSL target 1500 tomorrow. Guaranteed returns.",
    "Dont miss crudeoil trade.",
    "Happy birthday bro!",
]

print()
print("=" * 70)
print("CLASSIFIER OUTPUT")
print("=" * 70)
classifications = {}
for text in TEXTS:
    try:
        result = lc.classify_message(text)
    except Exception as exc:
        result = None
        print(f"\n{text!r}\n  ERROR: {exc}")
    classifications[text] = result
    if result is not None:
        print(f"\n{text!r}\n  {show(result)}")

print()
print("=" * 70)
print("MAP_IMPACT — CALLING CONVENTIONS")
print("=" * 70)
for text in TEXTS:
    cls = classifications.get(text)
    print(f"\n--- {text!r}")
    attempts = [
        ("map_impact(classification)", lambda: mp.map_impact(cls)),
        ("map_impact(text)", lambda: mp.map_impact(text)),
        ("map_impact(text, classification)", lambda: mp.map_impact(text, cls)),
        ("map_impact(classification, text)", lambda: mp.map_impact(cls, text)),
        ("map_impact(text=..., classification=...)",
         lambda: mp.map_impact(text=text, classification=cls)),
        ("map_impact(message=..., classification=...)",
         lambda: mp.map_impact(message=text, classification=cls)),
    ]
    for label, call in attempts:
        try:
            print(f"  {label:44} OK   {show(call())}")
        except TypeError as exc:
            print(f"  {label:44} TYPE {exc}")
        except Exception as exc:
            print(f"  {label:44} ERR  {type(exc).__name__}: {exc}")

print()
print("=" * 70)
print("MODULE SOURCE — map_impact")
print("=" * 70)
try:
    print(inspect.getsource(mp.map_impact)[:2500])
except Exception as exc:
    print(f"unavailable: {exc}")
