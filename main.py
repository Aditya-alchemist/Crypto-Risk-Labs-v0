from __future__ import annotations

import asyncio
import logging
import contextlib
from contextlib import asynccontextmanager
import re

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from telegram import BotCommand
from telegram.ext import Application

from bot.claude_brain import analyze_chart
from bot.config import settings
from bot.database import PatternStat, SessionLocal, TradeLog, init_db
from bot.handlers import BotServices, build_handlers, command_specs
from bot.historical_scanner import seed_pattern_stats_from_historical
from bot.levels import add_level, list_active_levels
from bot.monte_carlo import run_monte_carlo_distribution
from bot.pattern_engine import build_trade_plan
from bot.pattern_templates import resolve_template
from bot.price_watcher import PriceWatcher
from bot.self_learner import predict_trade_outcome
from bot.ws_manager import WebSocketManager

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)

ws_manager = WebSocketManager()
telegram_app: Application | None = None


class LevelCreate(BaseModel):
    price: float
    label: str = ""


class ChatAnalyzeRequest(BaseModel):
    prompt: str


async def telegram_alert(message: str) -> None:
    if not telegram_app or not settings.telegram_chat_id:
        return
    await telegram_app.bot.send_message(chat_id=settings.telegram_chat_id, text=message)


price_watcher = PriceWatcher(alert_callback=telegram_alert, broadcast_callback=ws_manager.broadcast_json)


def _extract_entry(text: str, fallback: float) -> float:
    match = re.search(r"(?:buy|entry|at)\s*(?:price\s*)?(?:=|:)?\s*\$?\s*(\d{4,8}(?:\.\d+)?)", text, flags=re.IGNORECASE)
    if not match:
        return fallback
    try:
        return float(match.group(1))
    except Exception:
        return fallback


def _volatility_from_candles(candles: list[list[float | int]]) -> float:
    if len(candles) < 2:
        return 0.002
    moves = []
    for c in candles:
        try:
            op = float(c[1])
            cl = float(c[4])
            moves.append(abs((cl - op) / op))
        except Exception:
            continue
    if not moves:
        return 0.002
    return max(sum(moves) / len(moves), 0.001)


def _pattern_metrics(pattern_name: str) -> tuple[float, int]:
    with SessionLocal() as session:
        row = session.query(PatternStat).filter(PatternStat.pattern == pattern_name).first()
    if not row:
        return 0.0, 0
    total = row.wins + row.losses
    return ((row.wins / total) * 100 if total else 0.0), total


def _contextual_pattern_metrics(pattern_name: str, side: str, volatility: float) -> tuple[float, int]:
    base_rate, base_samples = _pattern_metrics(pattern_name)
    with SessionLocal() as session:
        side_rows = session.query(TradeLog).filter(TradeLog.pattern == pattern_name, TradeLog.side == side).all()
        if volatility < 0.0018:
            lo, hi = 0.0, 0.0018
        elif volatility < 0.0035:
            lo, hi = 0.0018, 0.0035
        else:
            lo, hi = 0.0035, 999.0
        regime_rows = (
            session.query(TradeLog)
            .filter(TradeLog.volatility >= lo, TradeLog.volatility < hi)
            .order_by(TradeLog.created_at.desc())
            .limit(150)
            .all()
        )
        global_rows = session.query(PatternStat).all()

    side_samples = len(side_rows)
    side_rate = 0.0
    if side_samples:
        side_wins = sum(1 for t in side_rows if (t.result or "").upper() == "WIN")
        side_rate = (side_wins / side_samples) * 100

    regime_samples = len(regime_rows)
    regime_rate = 0.0
    if regime_samples:
        regime_wins = sum(1 for t in regime_rows if (t.result or "").upper() == "WIN")
        regime_rate = (regime_wins / regime_samples) * 100

    weighted_sum = 0.0
    weight_total = 0.0
    if base_samples:
        weighted_sum += base_rate * 0.50
        weight_total += 0.50
    if side_samples >= 3:
        weighted_sum += side_rate * 0.30
        weight_total += 0.30
    if regime_samples >= 8:
        weighted_sum += regime_rate * 0.20
        weight_total += 0.20

    if weight_total == 0.0:
        global_rates: list[float] = []
        global_samples = 0
        for row in global_rows:
            total = row.wins + row.losses
            if total <= 0:
                continue
            global_rates.append((row.wins / total) * 100)
            global_samples += total
        if global_rates:
            return sum(global_rates) / len(global_rates), global_samples
        return 50.0, 0

    return weighted_sum / weight_total, (base_samples + side_samples + regime_samples)


def _blend_confidence(historical_hit_rate: float, monte_carlo_prob: float, ml_confidence: float, historical_samples: int) -> float:
    sample_factor = min(historical_samples / 50.0, 1.0)
    calibrated_historical = (historical_hit_rate * sample_factor) + (50.0 * (1.0 - sample_factor))
    return max(0.0, min(100.0, (0.35 * calibrated_historical) + (0.40 * monte_carlo_prob) + (0.25 * ml_confidence)))


async def _start_telegram_bot() -> Application | None:
    if not settings.telegram_token:
        logger.warning("TELEGRAM_BOT_TOKEN missing, bot polling disabled")
        return None

    try:
        app = Application.builder().token(settings.telegram_token).build()
        app.bot_data["services"] = BotServices(price_watcher=price_watcher)

        for handler in build_handlers():
            app.add_handler(handler)

        await app.initialize()
        await app.start()
        await app.bot.set_my_commands([BotCommand(command=name, description=desc) for name, desc in command_specs()])
        if app.updater is not None:
            await app.updater.start_polling(allowed_updates=None)
        logger.info("Telegram bot started")
        return app
    except Exception:
        logger.exception("Telegram startup failed; continuing without Telegram")
        with contextlib.suppress(Exception):
            if app.updater is not None:
                await app.updater.stop()
            await app.stop()
            await app.shutdown()
        return None


async def _stop_telegram_bot(app: Application | None) -> None:
    if not app:
        return
    if app.updater is not None:
        await app.updater.stop()
    await app.stop()
    await app.shutdown()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global telegram_app
    init_db()
    scanner_result = seed_pattern_stats_from_historical()
    logger.info("Historical scanner seeded: %s", scanner_result)

    telegram_app = await _start_telegram_bot()
    watcher_task = asyncio.create_task(price_watcher.run(interval_seconds=settings.price_update_interval_seconds))

    try:
        yield
    finally:
        price_watcher.stop()
        watcher_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await watcher_task
        await _stop_telegram_bot(telegram_app)


app = FastAPI(title="CRL Bot API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/price")
async def get_price() -> dict[str, float | None]:
    if price_watcher.last_price is None:
        current = await price_watcher.fetch_price()
        return {"price": current}
    return {"price": price_watcher.last_price}


@app.get("/api/levels")
async def get_levels() -> list[dict[str, float | int | str]]:
    return [
        {
            "id": l.id,
            "price": l.price,
            "label": l.label,
            "direction": l.direction,
        }
        for l in list_active_levels()
    ]


@app.post("/api/levels")
async def create_level(payload: LevelCreate) -> dict[str, float | int | str]:
    level = add_level(payload.price, payload.label)
    await ws_manager.broadcast_json({"type": "level_added", "id": level.id, "price": level.price, "label": level.label})
    return {"id": level.id, "price": level.price, "label": level.label}


@app.get("/api/trades")
async def get_trades() -> list[dict[str, str | float | int]]:
    with SessionLocal() as session:
        rows = session.query(TradeLog).order_by(TradeLog.created_at.desc()).limit(200).all()
    return [
        {
            "id": t.id,
            "pattern": t.pattern,
            "side": t.side,
            "entry_price": t.entry_price,
            "result": t.result,
            "tp_hit": t.tp_hit,
            "rr": t.rr,
            "created_at": t.created_at.isoformat(),
        }
        for t in rows
    ]


@app.get("/api/pattern-stats")
async def get_pattern_stats() -> list[dict[str, str | int | float]]:
    from bot.database import PatternStat

    with SessionLocal() as session:
        rows = session.query(PatternStat).order_by(PatternStat.pattern.asc()).all()

    output = []
    for row in rows:
        total = row.wins + row.losses
        win_rate = (row.wins / total) * 100 if total else 0.0
        output.append(
            {
                "pattern": row.pattern,
                "wins": row.wins,
                "losses": row.losses,
                "samples": total,
                "win_rate": round(win_rate, 2),
            }
        )
    return output


@app.get("/api/analytics")
async def get_analytics() -> dict[str, float | int | str]:
    price = await price_watcher.fetch_price()
    candles = await price_watcher.fetch_recent_candles(limit=50)
    volatility = _volatility_from_candles(candles)
    momentum = 0.0
    if len(candles) >= 2:
        try:
            momentum = ((float(candles[0][4]) - float(candles[-1][4])) / float(candles[-1][4])) * 100
        except Exception:
            momentum = 0.0

    with SessionLocal() as session:
        trades_count = session.query(TradeLog).count()
        pattern_rows = session.query(PatternStat).all()
    avg_hit_rate = 0.0
    if pattern_rows:
        vals = []
        for p in pattern_rows:
            total = p.wins + p.losses
            if total:
                vals.append((p.wins / total) * 100)
        if vals:
            avg_hit_rate = sum(vals) / len(vals)

    return {
        "price": round(price, 2),
        "volatility_pct": round(volatility * 100, 3),
        "momentum_pct": round(momentum, 3),
        "trades_count": trades_count,
        "average_pattern_hit_rate": round(avg_hit_rate, 2),
    }


@app.get("/api/monte-carlo")
async def get_monte_carlo_preview() -> dict[str, object]:
    price = await price_watcher.fetch_price()
    candles = await price_watcher.fetch_recent_candles(limit=50)
    volatility = _volatility_from_candles(candles)
    tp = price * 1.012
    sl = price * 0.992
    distribution = run_monte_carlo_distribution(entry=price, tp=tp, sl=sl, volatility=volatility, simulations=300)

    return {
        "hit_tp_probability": round(distribution.result.hit_tp_probability, 2),
        "hit_sl_probability": round(distribution.result.hit_sl_probability, 2),
        "bins": distribution.bins,
    }


@app.post("/api/chat-analyze")
async def chat_analyze(payload: ChatAnalyzeRequest) -> dict[str, object]:
    prompt = payload.prompt.strip()
    if not prompt:
        return {"error": "Prompt is required."}

    ai = await analyze_chart(prompt, image_path=None)
    market_price = await price_watcher.fetch_price()
    side = "short" if "short" in prompt.lower() or str(ai.get("bias", "long")).lower() == "short" else "long"
    entry = _extract_entry(prompt, fallback=market_price)

    template = resolve_template(str(ai.get("pattern_template") or ai.get("pattern") or "generic"))
    levels = ai.get("key_levels", [])
    level_values = [float(x) for x in levels if isinstance(x, (int, float))]
    if level_values:
        nearest = min(level_values, key=lambda x: abs(x - entry))
    else:
        nearest = entry * (0.992 if side == "long" else 1.008)

    if side == "long":
        plan = build_trade_plan(
            pattern=template.display_name,
            side=side,
            entry=entry,
            swing_low=nearest,
            swing_high=entry + 10,
            stop_multiplier=template.stop_multiplier,
            tp_multipliers=template.tp_multipliers,
        )
    else:
        plan = build_trade_plan(
            pattern=template.display_name,
            side=side,
            entry=entry,
            swing_low=entry - 10,
            swing_high=nearest,
            stop_multiplier=template.stop_multiplier,
            tp_multipliers=template.tp_multipliers,
        )

    candles = await price_watcher.fetch_recent_candles(limit=50)
    volatility = _volatility_from_candles(candles)
    distribution = run_monte_carlo_distribution(
        entry=plan.entry,
        tp=plan.tp1,
        sl=plan.stop_loss,
        volatility=volatility,
        simulations=300,
    )
    ml = predict_trade_outcome(
        {
            "pattern": template.key,
            "side": side,
            "session": "unknown",
            "cycle": "unknown",
            "rr": round(plan.rr, 2),
            "volatility": volatility,
        }
    )

    hit_rate, samples = _contextual_pattern_metrics(template.key, side, volatility)
    blended = _blend_confidence(hit_rate, distribution.result.hit_tp_probability, float(ml["confidence"]), samples)

    message = (
        f"🧠 CRL Setup: {plan.pattern} ({plan.side})\n"
        f"💰 Market: ${market_price:,.2f}\n"
        f"🎯 Entry: ${plan.entry:,.2f} | TP1: ${plan.tp1:,.2f} | TP2: ${plan.tp2:,.2f} | TP3: ${plan.tp3:,.2f}\n"
        f"🛡️ Stop Loss: ${plan.stop_loss:,.2f} | RR: 1:{plan.rr:.2f}\n"
        f"📊 Confidence -> Monte Carlo: {distribution.result.hit_tp_probability:.1f}%, Historical: {hit_rate:.1f}%, ML: {float(ml['confidence']):.1f}%, Blended: {blended:.1f}%\n"
        "⚠️ Entry only on 5m candle CLOSE confirmation. Never trade on a wick."
    )

    return {
        "message": message,
        "plan": {
            "pattern": plan.pattern,
            "side": plan.side,
            "entry": round(plan.entry, 2),
            "tp1": round(plan.tp1, 2),
            "tp2": round(plan.tp2, 2),
            "tp3": round(plan.tp3, 2),
            "sl": round(plan.stop_loss, 2),
            "rr": round(plan.rr, 2),
        },
        "confidence": {
            "monte_carlo": round(distribution.result.hit_tp_probability, 2),
            "historical": round(hit_rate, 2),
            "ml": round(float(ml["confidence"]), 2),
            "blended": round(blended, 2),
        },
        "monte_carlo_bins": distribution.bins,
        "summary": ai.get("summary", ""),
    }


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect(ws)
