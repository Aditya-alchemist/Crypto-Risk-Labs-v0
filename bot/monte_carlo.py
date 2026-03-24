from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass
class MonteCarloResult:
    hit_tp_probability: float
    hit_sl_probability: float
    simulations: int


@dataclass
class MonteCarloDistribution:
    result: MonteCarloResult
    bins: list[dict[str, float | int]]
    terminal_prices: list[float]


def run_monte_carlo(entry: float, tp: float, sl: float, volatility: float, simulations: int = 300, steps: int = 50) -> MonteCarloResult:
    tp_hits = 0
    sl_hits = 0
    sigma = max(volatility, 0.001)

    for _ in range(simulations):
        price = entry
        resolved = False
        for _step in range(steps):
            drift = random.gauss(0.0, sigma)
            price += entry * drift
            if (tp > entry and price >= tp) or (tp < entry and price <= tp):
                tp_hits += 1
                resolved = True
                break
            if (sl < entry and price <= sl) or (sl > entry and price >= sl):
                sl_hits += 1
                resolved = True
                break

        if not resolved:
            if abs(price - tp) < abs(price - sl):
                tp_hits += 1
            else:
                sl_hits += 1

    hit_tp_probability = (tp_hits / simulations) * 100
    hit_sl_probability = (sl_hits / simulations) * 100
    return MonteCarloResult(hit_tp_probability=hit_tp_probability, hit_sl_probability=hit_sl_probability, simulations=simulations)


def run_monte_carlo_distribution(
    entry: float,
    tp: float,
    sl: float,
    volatility: float,
    simulations: int = 300,
    steps: int = 50,
    buckets: int = 20,
) -> MonteCarloDistribution:
    result = run_monte_carlo(entry=entry, tp=tp, sl=sl, volatility=volatility, simulations=simulations, steps=steps)

    sigma = max(volatility, 0.001)
    terminal_prices: list[float] = []
    for _ in range(simulations):
        price = entry
        for _step in range(steps):
            price += entry * random.gauss(0.0, sigma)
        terminal_prices.append(price)

    low = min(terminal_prices)
    high = max(terminal_prices)
    if high == low:
        high = low + 1e-6
    width = (high - low) / buckets

    counts = [0 for _ in range(buckets)]
    for value in terminal_prices:
        idx = int((value - low) / width)
        if idx >= buckets:
            idx = buckets - 1
        counts[idx] += 1

    bins = []
    for i, count in enumerate(counts):
        start = low + (i * width)
        end = start + width
        bins.append({"bin_start": round(start, 2), "bin_end": round(end, 2), "count": count})

    return MonteCarloDistribution(result=result, bins=bins, terminal_prices=terminal_prices)
