from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from bot.database import PatternStat, SessionLocal


@dataclass
class Candle:
    open: float
    high: float
    low: float
    close: float


def _read_candles(csv_path: Path, max_rows: int = 10000) -> list[Candle]:
    if not csv_path.exists():
        return []

    candles: list[Candle] = []
    with csv_path.open("r", encoding="utf-8", newline="") as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            try:
                candles.append(
                    Candle(
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                    )
                )
            except Exception:
                continue

            if len(candles) >= max_rows:
                break
    return candles


def _update_score(scores: dict[str, tuple[int, int]], key: str, is_win: bool) -> None:
    wins, losses = scores.get(key, (0, 0))
    if is_win:
        wins += 1
    else:
        losses += 1
    scores[key] = (wins, losses)


def _scan_patterns(candles: list[Candle]) -> dict[str, tuple[int, int]]:
    scores: dict[str, tuple[int, int]] = {}
    if len(candles) < 80:
        return scores

    for idx in range(30, len(candles) - 12):
        window = candles[idx - 20 : idx]
        current = candles[idx]
        future = candles[idx + 1 : idx + 11]
        if not future:
            continue

        prev_high = max(c.high for c in window)
        prev_low = min(c.low for c in window)
        range_size = max(prev_high - prev_low, 1e-9)

        sma20 = sum(c.close for c in window) / len(window)
        prev_close = candles[idx - 1].close

        # Box breakout long: close above local range high.
        if current.close > prev_high * 1.001:
            target = current.close + range_size
            stop = current.close - (range_size * 0.6)
            hit_target = any(c.high >= target for c in future)
            hit_stop = any(c.low <= stop for c in future)
            _update_score(scores, "box", hit_target and not hit_stop)

        # Box breakout short: close below local range low.
        if current.close < prev_low * 0.999:
            target = current.close - range_size
            stop = current.close + (range_size * 0.6)
            hit_target = any(c.low <= target for c in future)
            hit_stop = any(c.high >= stop for c in future)
            _update_score(scores, "box", hit_target and not hit_stop)

        # Mean reversion long from lower range edge.
        if current.low <= (prev_low + range_size * 0.1):
            target = current.close + (range_size * 0.5)
            stop = current.close - (range_size * 0.4)
            hit_target = any(c.high >= target for c in future)
            hit_stop = any(c.low <= stop for c in future)
            _update_score(scores, "channel", hit_target and not hit_stop)

        # Mean reversion short from upper range edge.
        if current.high >= (prev_high - range_size * 0.1):
            target = current.close - (range_size * 0.5)
            stop = current.close + (range_size * 0.4)
            hit_target = any(c.low <= target for c in future)
            hit_stop = any(c.high >= stop for c in future)
            _update_score(scores, "channel", hit_target and not hit_stop)

        # Trend pullback long.
        if prev_close > sma20 and current.low < sma20 and current.close > sma20:
            target = current.close + (range_size * 0.8)
            stop = current.close - (range_size * 0.5)
            hit_target = any(c.high >= target for c in future)
            hit_stop = any(c.low <= stop for c in future)
            _update_score(scores, "triangle", hit_target and not hit_stop)

        # Trend pullback short.
        if prev_close < sma20 and current.high > sma20 and current.close < sma20:
            target = current.close - (range_size * 0.8)
            stop = current.close + (range_size * 0.5)
            hit_target = any(c.low <= target for c in future)
            hit_stop = any(c.high >= stop for c in future)
            _update_score(scores, "triangle", hit_target and not hit_stop)

    return scores


def seed_pattern_stats_from_historical(csv_path: Path | None = None) -> dict[str, int]:
    source = csv_path or Path("data/historical/btc_daily.csv")
    candles = _read_candles(source)
    scores = _scan_patterns(candles)

    inserted = 0
    updated = 0
    with SessionLocal() as session:
        for pattern_name, (wins, losses) in scores.items():
            if wins + losses < 5:
                continue
            existing = session.query(PatternStat).filter_by(pattern=pattern_name).first()
            if existing is None:
                session.add(PatternStat(pattern=pattern_name, wins=wins, losses=losses))
                inserted += 1
            else:
                # Do not wipe manual logging; only top-up if scanner found stronger baseline.
                if (existing.wins + existing.losses) < (wins + losses):
                    existing.wins = wins
                    existing.losses = losses
                    updated += 1
        session.commit()

    return {"inserted": inserted, "updated": updated, "patterns": len(scores)}
