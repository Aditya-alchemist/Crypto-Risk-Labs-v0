from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PatternTemplate:
    key: str
    display_name: str
    stop_multiplier: float
    tp_multipliers: tuple[float, float, float]


TEMPLATES: dict[str, PatternTemplate] = {
    "box": PatternTemplate(key="box", display_name="Box Breakout", stop_multiplier=1.0, tp_multipliers=(1.4, 2.4, 3.6)),
    "triangle": PatternTemplate(
        key="triangle", display_name="Triangle Breakout", stop_multiplier=0.95, tp_multipliers=(1.6, 2.8, 4.1)
    ),
    "channel": PatternTemplate(key="channel", display_name="Channel Break", stop_multiplier=1.1, tp_multipliers=(1.3, 2.1, 3.2)),
    "flag": PatternTemplate(key="flag", display_name="Flag Continuation", stop_multiplier=0.9, tp_multipliers=(1.5, 2.6, 3.9)),
    "reversal": PatternTemplate(key="reversal", display_name="Reversal Setup", stop_multiplier=1.15, tp_multipliers=(1.2, 2.0, 3.0)),
    "generic": PatternTemplate(key="generic", display_name="Generic Structure", stop_multiplier=1.0, tp_multipliers=(1.5, 2.5, 3.8)),
}


ALIASES: dict[str, str] = {
    "box": "box",
    "rectangle": "box",
    "range": "box",
    "triangle": "triangle",
    "ascending triangle": "triangle",
    "descending triangle": "triangle",
    "sym triangle": "triangle",
    "channel": "channel",
    "parallel channel": "channel",
    "trend channel": "channel",
    "wedge": "triangle",
    "ascending wedge": "triangle",
    "descending wedge": "triangle",
    "flag": "flag",
    "bull flag": "flag",
    "bear flag": "flag",
    "pennant": "flag",
    "head and shoulders": "reversal",
    "inverse head and shoulders": "reversal",
    "double top": "reversal",
    "double bottom": "reversal",
    "support bounce": "reversal",
    "resistance rejection": "reversal",
    "breakout": "box",
    "sideways": "box",
    "consolidation": "box",
    "pullback": "channel",
    "trend continuation": "flag",
}


def resolve_template(pattern_text: str) -> PatternTemplate:
    text = (pattern_text or "").lower()
    for alias, key in ALIASES.items():
        if alias in text:
            return TEMPLATES[key]
    return TEMPLATES["generic"]
