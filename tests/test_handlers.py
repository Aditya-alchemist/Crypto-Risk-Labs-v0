from __future__ import annotations

from types import SimpleNamespace

import pytest

import bot.handlers as handlers
from bot.database import PatternStat, TradeLog


class DummyMessage:
    def __init__(self):
        self.replies: list[str] = []

    async def reply_text(self, text: str) -> None:
        self.replies.append(text)


class DummyUpdate:
    def __init__(self):
        self.effective_message = DummyMessage()
        self.message = self.effective_message


@pytest.mark.asyncio
async def test_log_command_records_trade_and_stats(monkeypatch, test_session):
    monkeypatch.setattr(handlers, "SessionLocal", test_session)
    monkeypatch.setattr(handlers, "maybe_retrain_model", lambda: False)

    update = DummyUpdate()
    context = SimpleNamespace(args=["box_breakout", "long", "84200", "WIN", "TP2"])

    await handlers.log_cmd(update, context)

    with test_session() as session:
        trades = session.query(TradeLog).all()
        stats = session.query(PatternStat).all()

    assert len(trades) == 1
    assert trades[0].pattern == "box_breakout"
    assert trades[0].result == "WIN"
    assert len(stats) == 1
    assert stats[0].wins == 1
    assert "Logged trade" in update.effective_message.replies[-1]


@pytest.mark.asyncio
async def test_analyze_output_contains_warning(monkeypatch):
    class DummyWatcher:
        async def fetch_recent_candles(self, limit=200):
            return [[0, "100", "103", "99", "101", "0", 0, 0, 0, 0, 0, 0]] * limit

        async def fetch_price(self):
            return 84200.0

    monkeypatch.setattr(
        handlers,
        "run_monte_carlo",
        lambda **kwargs: SimpleNamespace(hit_tp_probability=68.0),
    )
    monkeypatch.setattr(
        handlers,
        "predict_trade_outcome",
        lambda features: {"verdict": "WIN", "confidence": 71.0},
    )
    monkeypatch.setattr(handlers, "_get_pattern_metrics", lambda pattern_name: (62.0, 40))

    update = DummyUpdate()
    context = SimpleNamespace(
        args=["box_breakout", "long", "84200", "84100"],
        bot_data={"services": SimpleNamespace(price_watcher=DummyWatcher())},
    )

    await handlers.analyze_cmd(update, context)

    last_message = update.effective_message.replies[-1]
    assert "CRL BOT ANALYSIS" in last_message
    assert "Monte Carlo (300): 68.0%" in last_message
    assert "Historical hit-rate: 62.0%" in last_message
    assert "Blended confidence:" in last_message
    assert handlers.WARNING_LINE in last_message


@pytest.mark.asyncio
async def test_tradeidea_text_pipeline(monkeypatch):
    monkeypatch.setattr(
        handlers,
        "_run_strict_pipeline",
        lambda context, user_text, image_path=None: (
            __import__("asyncio").sleep(0, result="CRL BOT ANALYSIS\nBlended confidence: 67.5%\n" + handlers.WARNING_LINE)
        ),
    )

    update = DummyUpdate()
    context = SimpleNamespace(args=["buying", "at", "84200", "box", "breakout"], bot_data={})

    await handlers.tradeidea_cmd(update, context)

    last_message = update.effective_message.replies[-1]
    assert "CRL BOT ANALYSIS" in last_message
    assert "Blended confidence: 67.5%" in last_message
    assert handlers.WARNING_LINE in last_message


@pytest.mark.asyncio
async def test_natural_text_handler_works(monkeypatch):
    monkeypatch.setattr(
        handlers,
        "_run_strict_pipeline",
        lambda context, user_text, image_path=None: __import__("asyncio").sleep(0, result="CRL BOT ANALYSIS"),
    )

    update = DummyUpdate()
    update.message.text = "i want to buy at current price analyze market"
    context = SimpleNamespace(bot_data={})

    await handlers.natural_text_handler(update, context)

    assert update.effective_message.replies[-1] == "CRL BOT ANALYSIS"


@pytest.mark.asyncio
async def test_analyze_natural_language_many_words(monkeypatch):
    monkeypatch.setattr(
        handlers,
        "_run_strict_pipeline",
        lambda context, user_text, image_path=None: __import__("asyncio").sleep(0, result="CRL BOT ANALYSIS"),
    )

    update = DummyUpdate()
    context = SimpleNamespace(args=["i", "want", "to", "buy", "at", "current", "price", "analyze", "market"], bot_data={})

    await handlers.analyze_cmd(update, context)

    assert update.effective_message.replies[-1] == "CRL BOT ANALYSIS"
