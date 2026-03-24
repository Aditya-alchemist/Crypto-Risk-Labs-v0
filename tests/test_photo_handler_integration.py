from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import bot.claude_brain as claude_brain
import bot.handlers as handlers


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self):
        payload = {
            "pattern": "Box breakout",
            "pattern_template": "box",
            "bias": "long",
            "key_levels": [84000, 84500],
            "entry_hint": "buying at 84200",
            "summary": "Box breakout confirmed on 5m close.",
        }
        return {"choices": [{"message": {"content": json.dumps(payload)}}]}


class FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, *args, **kwargs):
        return FakeResponse()


class DummyDownloadedFile:
    async def download_to_drive(self, custom_path: str) -> None:
        Path(custom_path).write_bytes(b"fake image bytes")


class DummyPhoto:
    async def get_file(self):
        return DummyDownloadedFile()


class DummyMessage:
    def __init__(self, caption: str):
        self.photo = [DummyPhoto()]
        self.caption = caption
        self.replies: list[str] = []

    async def reply_text(self, text: str) -> None:
        self.replies.append(text)


class DummyUpdate:
    def __init__(self, caption: str):
        self.message = DummyMessage(caption)
        self.effective_message = self.message


class DummyWatcher:
    async def fetch_price(self):
        return 84312.0

    async def fetch_recent_candles(self, limit=200):
        return [[0, "84300", "84420", "84210", "84380", "0", 0, 0, 0, 0, 0, 0]] * limit


@pytest.mark.asyncio
async def test_photo_handler_with_mocked_openrouter(monkeypatch):
    monkeypatch.setattr(claude_brain, "httpx", SimpleNamespace(AsyncClient=FakeAsyncClient))
    monkeypatch.setattr(
        claude_brain,
        "settings",
        SimpleNamespace(openrouter_api_key="test-key", openrouter_model="anthropic/claude-3.5-sonnet"),
    )
    monkeypatch.setattr(handlers, "analyze_chart", claude_brain.analyze_chart)
    monkeypatch.setattr(handlers, "_get_pattern_metrics", lambda pattern_name: (66.0, 55))
    monkeypatch.setattr(
        handlers,
        "run_monte_carlo",
        lambda **kwargs: SimpleNamespace(hit_tp_probability=69.0),
    )
    monkeypatch.setattr(
        handlers,
        "predict_trade_outcome",
        lambda features: {"verdict": "WIN", "confidence": 73.5},
    )

    update = DummyUpdate("I am buying at 84200 on this chart")
    context = SimpleNamespace(bot_data={"services": SimpleNamespace(price_watcher=DummyWatcher())})

    await handlers.photo_analysis_handler(update, context)

    assert update.message.replies
    message = update.message.replies[-1]
    assert "CRL BOT ANALYSIS" in message
    assert "Entry Zone: $84,200.00" in message
    assert "Historical hit-rate: 66.0%" in message
    assert "Monte Carlo (300): 69.0%" in message
    assert "ML model: WIN (73.50%)" in message
    assert "Blended confidence:" in message
    assert handlers.WARNING_LINE in message
