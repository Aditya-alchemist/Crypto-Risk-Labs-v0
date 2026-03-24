# CRL Bot

CRL Bot is a personal BTC trading intelligence system with:
- Telegram bot interface for mobile workflows
- FastAPI backend for services and data
- React dashboard for desktop monitoring
- Starter self-learning and simulation modules

## Current Status (Starter Build)

This repository now includes:
- Async Binance BTC price watcher (30s loop)
- SQLite schema for levels, crossings, and trade logs
- Telegram commands: `/start`, `/help`, `/price`, `/levels`, `/addlevel`, `/log`, `/analyze`, `/tradeidea`, `/model`, `/patterns`
- Telegram photo upload flow for chart image analysis via OpenRouter Claude vision
- FastAPI REST endpoints and WebSocket stream
- Monte Carlo simulation scaffold (300 runs)
- Weighted confidence blend from historical hit-rate, Monte Carlo, and ML confidence
- RandomForest training/prediction scaffold
- Historical scanner to seed pattern stats from CSV history
- React dashboard with TradingView Lightweight Charts + Binance 5m candlestick stream
- Automated tests for price crossing, logging, analyze formatting, photo integration, and API endpoints

Note: On Python 3.14, some ML libraries may not have stable wheels yet. The self-learner includes a fallback mode that still tracks and predicts from empirical win-rate data.

## Project Structure

- `main.py` - starts FastAPI and Telegram polling
- `bot/` - bot + engines + DB modules
- `data/` - CRL knowledge rules, db, historical csv placeholders
- `dashboard/` - React + Vite frontend
- `scripts/` - history downloader

## Quick Start

### 1) Backend

```bash
cd crl-bot
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn main:app --reload --port 8000
```

### 2) Dashboard

```bash
cd dashboard
npm install
npm run dev
```

Set `VITE_BACKEND_URL` if backend is not `http://localhost:8000`.

## OpenRouter Key Placement

Yes, the correct environment key is OPENROUTER_API_KEY in your local .env file.

Do not commit real keys to .env.example or git.

## Image-To-Decision Flow

When user sends an image and caption like "I am buying at 84200":

1. Telegram photo handler downloads chart image.
2. Claude Vision (OpenRouter) extracts structured setup JSON.
3. Pattern template normalizer maps setup to box, triangle, channel, or generic.
4. Entry is parsed from user caption (fallback to live market price).
5. Historical hit-rate for mapped pattern is loaded from internal stats database.
6. Monte Carlo sim runs with current volatility from recent 5m candles.
7. Self-learner returns model verdict and confidence.
8. Bot replies with targets, stop loss, RR, confidence, and safety rule.

For text-only signals, use /tradeidea with plain language, for example:

"/tradeidea buying at 84200 after box breakout"

You can also send plain natural text without any slash command, for example:

"i want to buy at current price, analyze the market"

## Historical BTC Data Location

- Raw historical CSV files are stored in data/historical/btc_daily.csv and data/historical/btc_5min.csv.
- Download script: scripts/download_history.py
- Historical pattern seeding script: scripts/seed_pattern_stats.py
- Seeded pattern stats are persisted in SQLite table pattern_stats inside data/crl.db.

## Currently Recognized Baseline Patterns

Scanner currently seeds these universal baseline categories from historical candles:
- box
- triangle
- channel

These provide a baseline prior. Your live /log results continue adapting pattern stats over time.

## Internal Model Self-Response

Use /model in Telegram to make CRL Bot report its own internal state:
- whether a trained model file exists
- fallback profile status
- trade sample count
- current fallback win-rate
- top learned patterns from internal database stats

This is the bot replying based on its own learned state, not only Claude text generation.

## Railway Deployment

Use root folder `crl-bot` with Procfile:

```txt
web: uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
```

## Next Build Steps

1. Add chart-pattern extraction rules to convert Claude text into stricter structured levels and zones.
2. Add confidence calibration by combining scanner priors, Monte Carlo outputs, and logged outcomes.
3. Add migration/versioning for database schema and richer trade metadata.
4. Expand test suite to cover photo handler and API endpoints.
5. Add production observability and alert retry logic.

## Safety Rule

Every analysis output must include:

`WARNING: Entry only on 5m candle CLOSE confirmation. Never trade on a wick.`
