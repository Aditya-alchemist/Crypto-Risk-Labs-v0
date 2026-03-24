from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

import httpx

from bot.config import settings
from bot.database import CrossEvent, SessionLocal
from bot.levels import list_active_levels

logger = logging.getLogger(__name__)

AlertCallback = Callable[[str], Awaitable[None]]
BroadcastCallback = Callable[[dict[str, Any]], Awaitable[None]]


class PriceWatcher:
    def __init__(self, alert_callback: AlertCallback | None = None, broadcast_callback: BroadcastCallback | None = None) -> None:
        self._alert_callback = alert_callback
        self._broadcast_callback = broadcast_callback
        self._running = False
        self._last_price: float | None = None

    @property
    def last_price(self) -> float | None:
        return self._last_price

    async def _scan_fields(self, columns: list[str]) -> list[Any]:
        payload = {
            "symbols": {"tickers": [settings.tradingview_symbol], "query": {"types": []}},
            "columns": columns,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(settings.tradingview_scan_url, json=payload)
            response.raise_for_status()
            data = response.json()

        rows = data.get("data", []) if isinstance(data, dict) else []
        if not rows:
            raise RuntimeError("TradingView scan returned no rows")
        values = rows[0].get("d", [])
        if not isinstance(values, list):
            raise RuntimeError("TradingView scan response malformed")
        return values

    async def fetch_price(self) -> float:
        values = await self._scan_fields(["close"])
        return float(values[0])

    async def fetch_recent_candles(self, limit: int = 200) -> list[list[Any]]:
        # TradingView scanner doesn't expose full candle history in this API.
        # We build a compact multi-timeframe OHLC snapshot for volatility estimation.
        timeframes = ["1", "5", "15", "30", "60", "120", "240", "1D"]
        columns = []
        for tf in timeframes:
            columns.extend([f"open|{tf}", f"high|{tf}", f"low|{tf}", f"close|{tf}"])

        values = await self._scan_fields(columns)
        now_ms = int(datetime.utcnow().timestamp() * 1000)
        candles: list[list[Any]] = []
        for idx, tf in enumerate(timeframes):
            offset = idx * 4
            try:
                open_price = float(values[offset])
                high_price = float(values[offset + 1])
                low_price = float(values[offset + 2])
                close_price = float(values[offset + 3])
            except Exception:
                continue

            ts = now_ms - (idx * 5 * 60 * 1000)
            candles.append([ts, open_price, high_price, low_price, close_price, 0, ts + 1, 0, 0, 0, 0, 0])

        if len(candles) < 2:
            # Fallback to duplicated latest value so downstream logic always works.
            price = await self.fetch_price()
            candles = [
                [now_ms, price, price, price, price, 0, now_ms + 1, 0, 0, 0, 0, 0],
                [now_ms - 300000, price, price, price, price, 0, now_ms - 299999, 0, 0, 0, 0, 0],
            ]

        return candles[: max(2, min(limit, len(candles)))]

    async def run(self, interval_seconds: int = 30) -> None:
        self._running = True
        logger.info("Price watcher started with interval=%ss", interval_seconds)
        while self._running:
            try:
                await self._tick()
            except Exception:
                logger.exception("Price watcher tick failed")
            await asyncio.sleep(interval_seconds)

    def stop(self) -> None:
        self._running = False

    async def _tick(self) -> None:
        current_price = await self.fetch_price()
        previous_price = self._last_price
        self._last_price = current_price

        if self._broadcast_callback:
            await self._broadcast_callback(
                {
                    "type": "price_update",
                    "price": current_price,
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )

        if previous_price is None:
            return

        crossed_levels = []
        for level in list_active_levels():
            if min(previous_price, current_price) <= level.price <= max(previous_price, current_price):
                crossed_levels.append(level)

        if not crossed_levels:
            return

        with SessionLocal() as session:
            for level in crossed_levels:
                session.add(CrossEvent(level_id=level.id, level_price=level.price, touched_price=current_price))
            session.commit()

        for level in crossed_levels:
            message = f"BTC crossed level {level.price:.2f} ({level.label or 'unnamed'})"
            if self._alert_callback:
                await self._alert_callback(message)
            if self._broadcast_callback:
                await self._broadcast_callback(
                    {
                        "type": "level_cross",
                        "level_id": level.id,
                        "level_price": level.price,
                        "touched_price": current_price,
                    }
                )
