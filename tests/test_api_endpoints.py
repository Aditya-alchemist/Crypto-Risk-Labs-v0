from __future__ import annotations

from fastapi.testclient import TestClient

import main as app_main
from bot.database import PatternStat, TradeLog


def _patch_lifespan_dependencies(monkeypatch, test_session) -> None:
    async def _noop_start_telegram_bot():
        return None

    async def _noop_stop_telegram_bot(_app):
        return None

    async def _noop_watcher_run(interval_seconds=30):
        return None

    monkeypatch.setattr(app_main, "SessionLocal", test_session)
    monkeypatch.setattr(app_main, "init_db", lambda: None)
    monkeypatch.setattr(app_main, "seed_pattern_stats_from_historical", lambda: {"inserted": 0, "updated": 0, "patterns": 0})
    monkeypatch.setattr(app_main, "_start_telegram_bot", _noop_start_telegram_bot)
    monkeypatch.setattr(app_main, "_stop_telegram_bot", _noop_stop_telegram_bot)
    monkeypatch.setattr(app_main.price_watcher, "run", _noop_watcher_run)
    monkeypatch.setattr(app_main.price_watcher, "stop", lambda: None)


def test_api_pattern_stats(monkeypatch, test_session):
    _patch_lifespan_dependencies(monkeypatch, test_session)

    with test_session() as session:
        session.add(PatternStat(pattern="box", wins=18, losses=12))
        session.commit()

    with TestClient(app_main.app) as client:
        response = client.get("/api/pattern-stats")

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert payload[0]["pattern"] == "box"
    assert payload[0]["samples"] == 30
    assert payload[0]["win_rate"] == 60.0


def test_api_trades(monkeypatch, test_session):
    _patch_lifespan_dependencies(monkeypatch, test_session)

    with test_session() as session:
        session.add(
            TradeLog(
                pattern="box",
                side="long",
                entry_price=84200.0,
                result="WIN",
                tp_hit="TP2",
                rr=2.8,
            )
        )
        session.commit()

    with TestClient(app_main.app) as client:
        response = client.get("/api/trades")

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert payload[0]["pattern"] == "box"
    assert payload[0]["side"] == "long"
    assert payload[0]["result"] == "WIN"
