from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bot.database import PatternStat, SessionLocal, TradeLog

MODEL_PATH = Path("data/ml_model.pkl")
FALLBACK_PATH = Path("data/ml_fallback.json")


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _calibrated_probability(base_win_prob: float, features: dict[str, Any]) -> float:
    # Calibration makes fallback confidence react to trade context when no trained model exists.
    rr = float(features.get("rr", 2.0) or 2.0)
    volatility = float(features.get("volatility", 0.002) or 0.002)
    session_name = str(features.get("session", "")).lower()

    rr_adjustment = _clamp((2.0 - rr) * 0.04, -0.12, 0.12)
    volatility_adjustment = _clamp((0.003 - volatility) * 18.0, -0.08, 0.08)
    session_adjustment = 0.02 if session_name in {"london", "newyork", "ny"} else 0.0

    calibrated = base_win_prob + rr_adjustment + volatility_adjustment + session_adjustment
    return _clamp(calibrated, 0.08, 0.92)


def _build_model() -> Any:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.feature_extraction import DictVectorizer
    from sklearn.pipeline import Pipeline

    clf = RandomForestClassifier(n_estimators=200, random_state=42)
    return Pipeline([("vec", DictVectorizer(sparse=False)), ("clf", clf)])


def _extract_features(trade: TradeLog) -> dict[str, Any]:
    return {
        "pattern": trade.pattern,
        "side": trade.side,
        "session": trade.session_name,
        "cycle": trade.market_cycle,
        "rr": round(trade.rr, 2),
        "volatility": round(trade.volatility, 5),
    }


def maybe_retrain_model(min_samples: int = 30, cadence: int = 10) -> bool:
    with SessionLocal() as session:
        trades = session.query(TradeLog).all()

    if len(trades) < min_samples or len(trades) % cadence != 0:
        return False

    # Always persist a simple fallback estimate that works without sklearn.
    wins = sum(1 for t in trades if t.result.lower() == "win")
    fallback = {"win_rate": round((wins / len(trades)) * 100, 2), "samples": len(trades)}
    FALLBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    FALLBACK_PATH.write_text(json.dumps(fallback), encoding="utf-8")

    try:
        import joblib
    except Exception:
        return False

    x = [_extract_features(t) for t in trades]
    y = [1 if t.result.lower() == "win" else 0 for t in trades]

    try:
        model = _build_model()
        model.fit(x, y)
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, MODEL_PATH)
        return True
    except Exception:
        return False


def predict_trade_outcome(features: dict[str, Any]) -> dict[str, float | str]:
    try:
        import joblib
    except Exception:
        joblib = None

    if joblib and MODEL_PATH.exists():
        model = joblib.load(MODEL_PATH)
        probs = model.predict_proba([features])[0]
        win_prob = float(probs[1]) if len(probs) > 1 else 0.0
        if 0.49 <= win_prob <= 0.51:
            win_prob = _calibrated_probability(win_prob, features)
        verdict = "WIN" if win_prob >= 0.5 else "LOSS"
        return {"verdict": verdict, "confidence": round(win_prob * 100, 2)}

    if FALLBACK_PATH.exists():
        payload = json.loads(FALLBACK_PATH.read_text(encoding="utf-8"))
        win_prob = float(payload.get("win_rate", 0.0)) / 100.0
        win_prob = _calibrated_probability(win_prob, features)
        verdict = "WIN" if win_prob >= 0.5 else "LOSS"
        return {"verdict": verdict, "confidence": round(win_prob * 100, 2)}

    # Pattern-specific historical fallback before defaulting to 50/50.
    pattern_name = str(features.get("pattern", "")).strip()
    if pattern_name:
        with SessionLocal() as session:
            row = session.query(PatternStat).filter(PatternStat.pattern == pattern_name).first()
        if row:
            samples = row.wins + row.losses
            if samples > 0:
                win_prob = row.wins / samples
                win_prob = _calibrated_probability(win_prob, features)
                verdict = "WIN" if win_prob >= 0.5 else "LOSS"
                return {"verdict": verdict, "confidence": round(win_prob * 100, 2)}

    # Last resort before enough logged data exists.
    win_prob = _calibrated_probability(0.5, features)
    verdict = "WIN" if win_prob >= 0.5 else "LOSS"
    return {"verdict": verdict, "confidence": round(win_prob * 100, 2)}


def describe_model_state() -> dict[str, Any]:
    state: dict[str, Any] = {
        "has_trained_model": MODEL_PATH.exists(),
        "has_fallback": FALLBACK_PATH.exists(),
        "samples": 0,
        "fallback_win_rate": 0.0,
    }

    with SessionLocal() as session:
        trades = session.query(TradeLog).count()
    state["samples"] = trades

    if FALLBACK_PATH.exists():
        try:
            payload = json.loads(FALLBACK_PATH.read_text(encoding="utf-8"))
            state["fallback_win_rate"] = float(payload.get("win_rate", 0.0))
        except Exception:
            state["fallback_win_rate"] = 0.0

    return state
