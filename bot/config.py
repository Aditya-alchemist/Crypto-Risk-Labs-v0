from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    telegram_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    openrouter_api_key_backup: str = os.getenv("OPENROUTER_API_KEY1", os.getenv("OPENAI_API_KEY1", ""))
    openrouter_model: str = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_api_key_backup: str = os.getenv("GEMINI_API_KEY1", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///data/crl.db")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    tradingview_scan_url: str = os.getenv("TRADINGVIEW_SCAN_URL", "https://scanner.tradingview.com/crypto/scan")
    tradingview_symbol: str = os.getenv("TRADINGVIEW_SYMBOL", "BITSTAMP:BTCUSD")
    backend_url: str = os.getenv("BACKEND_URL", "http://localhost:8000")
    price_update_interval_seconds: int = int(os.getenv("PRICE_UPDATE_INTERVAL_SECONDS", "1"))


settings = Settings()
