from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PatternResult:
    pattern: str
    side: str
    entry: float
    stop_loss: float
    tp1: float
    tp2: float
    tp3: float
    rr: float


def build_trade_plan(
    pattern: str,
    side: str,
    entry: float,
    swing_low: float,
    swing_high: float,
    stop_multiplier: float = 1.0,
    tp_multipliers: tuple[float, float, float] = (1.5, 2.5, 3.8),
) -> PatternResult:
    side = side.lower()
    risk = abs(entry - swing_low) if side == "long" else abs(swing_high - entry)
    risk *= max(stop_multiplier, 0.2)
    if risk <= 0:
        risk = entry * 0.005

    tp1_mult, tp2_mult, tp3_mult = tp_multipliers

    if side == "long":
        stop = entry - risk
        tp1 = entry + (risk * tp1_mult)
        tp2 = entry + (risk * tp2_mult)
        tp3 = entry + (risk * tp3_mult)
    else:
        stop = entry + risk
        tp1 = entry - (risk * tp1_mult)
        tp2 = entry - (risk * tp2_mult)
        tp3 = entry - (risk * tp3_mult)

    rr = abs((tp3 - entry) / (entry - stop))
    return PatternResult(
        pattern=pattern,
        side=side,
        entry=entry,
        stop_loss=stop,
        tp1=tp1,
        tp2=tp2,
        tp3=tp3,
        rr=rr,
    )
