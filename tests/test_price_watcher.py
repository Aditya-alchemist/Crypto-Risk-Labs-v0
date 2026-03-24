from __future__ import annotations

from types import SimpleNamespace

import pytest

import bot.price_watcher as price_watcher_module
from bot.database import CrossEvent
from bot.price_watcher import PriceWatcher


@pytest.mark.asyncio
async def test_price_crossing_creates_event_and_alert(monkeypatch, test_session):
    monkeypatch.setattr(price_watcher_module, "SessionLocal", test_session)
    monkeypatch.setattr(
        price_watcher_module,
        "list_active_levels",
        lambda: [SimpleNamespace(id=1, price=100.0, label="test-level")],
    )

    alerts: list[str] = []

    async def alert_callback(message: str) -> None:
        alerts.append(message)

    watcher = PriceWatcher(alert_callback=alert_callback)
    watcher._last_price = 99.0

    async def fake_fetch_price() -> float:
        return 101.0

    watcher.fetch_price = fake_fetch_price

    await watcher._tick()

    with test_session() as session:
        events = session.query(CrossEvent).all()

    assert len(events) == 1
    assert events[0].level_price == 100.0
    assert alerts
    assert "crossed level" in alerts[0]
