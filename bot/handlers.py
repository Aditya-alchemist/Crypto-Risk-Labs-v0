from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import tempfile
from typing import Any

import httpx
from telegram import Update
from telegram.ext import BaseHandler, CommandHandler, ContextTypes, MessageHandler, filters

from bot.claude_brain import analyze_chart
from bot.config import settings
from bot.database import PatternStat, SessionLocal, TradeLog
from bot.levels import add_level, list_active_levels
from bot.monte_carlo import run_monte_carlo
from bot.pattern_engine import build_trade_plan
from bot.pattern_templates import resolve_template
from bot.self_learner import describe_model_state, maybe_retrain_model, predict_trade_outcome

WARNING_LINE = "⚠️ Entry only on 5m candle CLOSE confirmation. Never trade on a wick."


@dataclass
class BotServices:
    price_watcher: any


def command_specs() -> list[tuple[str, str]]:
    return [
        ("start", "Show welcome and quick commands"),
        ("help", "Show beginner examples"),
        ("price", "Show current BTCUSDT price"),
        ("levels", "List watched price levels"),
        ("addlevel", "Add watched level: /addlevel 84200 box_top"),
        ("tradeidea", "Natural language idea: /tradeidea buying near support"),
        ("analyze", "Legacy numeric mode or natural language mode"),
        ("patterns", "Show learned pattern stats"),
        ("model", "Show internal model state"),
        ("log", "Log outcome: /log box long 84200 WIN TP2"),
    ]


def _volatility_from_candles(candles: list[list[Any]]) -> float:
    if len(candles) < 2:
        return 0.002
    moves = []
    for row in candles:
        try:
            open_price = float(row[1])
            close_price = float(row[4])
            moves.append(abs((close_price - open_price) / open_price))
        except Exception:
            continue
    if not moves:
        return 0.002
    return max(sum(moves) / len(moves), 0.001)


def _pick_swing_ref(side: str, entry: float, levels: list[float]) -> float:
    if not levels:
        return entry * (0.992 if side == "long" else 1.008)

    if side == "long":
        below = [l for l in levels if l < entry]
        return max(below) if below else min(levels)

    above = [l for l in levels if l > entry]
    return min(above) if above else max(levels)


def _extract_entry_from_text(text: str, fallback: float) -> float:
    if not text:
        return fallback
    patterns = [
        r"(?:buy(?:ing)?|long|entry|at)\s*(?:price\s*)?(?:=|:)?\s*\$?\s*(\d{4,8}(?:\.\d+)?)",
        r"\$\s*(\d{4,8}(?:\.\d+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            try:
                return float(match.group(1).replace(",", ""))
            except Exception:
                continue
    return fallback


def _derive_entry_price(user_text: str, ai_payload: dict[str, Any], market_price: float, side: str) -> float:
    # 1) Prefer explicit user-provided entry.
    parsed = _extract_entry_from_text(user_text, fallback=-1.0)
    if parsed > 0:
        return parsed

    # 2) Use AI-provided entry hint if it contains a numeric level.
    entry_hint = str(ai_payload.get("entry_hint", ""))
    hinted = _extract_entry_from_text(entry_hint, fallback=-1.0)
    if hinted > 0:
        return hinted

    # 3) Use nearest structural level from AI levels.
    levels = ai_payload.get("key_levels", [])
    numeric = []
    if isinstance(levels, list):
        for value in levels:
            try:
                numeric.append(float(value))
            except Exception:
                continue
    if numeric:
        nearest = min(numeric, key=lambda x: abs(x - market_price))
        return nearest

    # 4) Last fallback: require slight confirmation offset instead of raw market equality.
    if side == "long":
        return market_price * 1.001
    return market_price * 0.999


def _extract_side_from_text(text: str, ai_bias: str) -> str:
    source = (text or "").lower()
    if "short" in source or "sell" in source or "selling" in source:
        return "short"
    if "long" in source or "buy" in source or "buying" in source:
        return "long"
    return "short" if ai_bias == "short" else "long"


def _normalize_user_prompt(text: str) -> str:
    source = (text or "").strip()
    if not source:
        return "Analyze BTC market structure and propose a safe trade plan."
    lowered = source.lower()
    if any(token in lowered for token in ["analyze", "analysis", "market", "buy", "sell", "long", "short"]):
        return source
    return f"Analyze BTC market based on this message: {source}"


async def _fetch_pattern_stats_from_api() -> list[dict[str, Any]]:
    endpoint = f"{settings.backend_url.rstrip('/')}/api/pattern-stats"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(endpoint)
        response.raise_for_status()
        payload = response.json()
    if isinstance(payload, list):
        return payload
    return []


def _fallback_pattern_stats() -> list[dict[str, Any]]:
    with SessionLocal() as session:
        rows = session.query(PatternStat).order_by((PatternStat.wins + PatternStat.losses).desc()).all()
    output = []
    for row in rows:
        samples = row.wins + row.losses
        output.append(
            {
                "pattern": row.pattern,
                "wins": row.wins,
                "losses": row.losses,
                "samples": samples,
                "win_rate": round((row.wins / samples) * 100, 2) if samples else 0.0,
            }
        )
    return output


def _get_pattern_hit_rate(pattern_name: str) -> float:
    with SessionLocal() as session:
        row = session.query(PatternStat).filter(PatternStat.pattern == pattern_name).first()
    if not row:
        return 0.0
    samples = row.wins + row.losses
    return (row.wins / samples) * 100 if samples else 0.0


def _get_pattern_metrics(pattern_name: str) -> tuple[float, int]:
    with SessionLocal() as session:
        row = session.query(PatternStat).filter(PatternStat.pattern == pattern_name).first()
    if not row:
        return 0.0, 0
    samples = row.wins + row.losses
    win_rate = (row.wins / samples) * 100 if samples else 0.0
    return win_rate, samples


def _get_contextual_historical_metrics(pattern_name: str, side: str, volatility: float) -> tuple[float, int]:
    base_rate, base_samples = _get_pattern_metrics(pattern_name)

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
        return 50.0, 0

    blended_rate = weighted_sum / weight_total
    combined_samples = base_samples + side_samples + regime_samples
    return blended_rate, combined_samples


def _blend_confidence(historical_hit_rate: float, monte_carlo_prob: float, ml_confidence: float, historical_samples: int) -> float:
    sample_factor = min(historical_samples / 50.0, 1.0)
    calibrated_historical = (historical_hit_rate * sample_factor) + (50.0 * (1.0 - sample_factor))
    blended = (0.35 * calibrated_historical) + (0.40 * monte_carlo_prob) + (0.25 * ml_confidence)
    return max(0.0, min(100.0, blended))


def _format_analysis_text(
    plan: Any,
    market_price: float,
    monte_carlo_prob: float,
    historical_hit_rate: float,
    blended_confidence: float,
    ml_verdict: str,
    ml_confidence: float,
    summary: str,
) -> str:
    verdict = "STRONG EDGE" if blended_confidence >= 65 else "MODERATE EDGE" if blended_confidence >= 55 else "LOW EDGE"
    return (
        f"🧠 CRL BOT ANALYSIS\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📌 Setup: {plan.pattern} ({plan.side})\n"
        f"💰 Market Price: ${market_price:,.2f}\n\n"
        f"🎯 TRADE PLAN\n"
        f"Entry Zone: ${plan.entry:,.2f}\n"
        f"Target 1: ${plan.tp1:,.2f}\n"
        f"Target 2: ${plan.tp2:,.2f}\n"
        f"Target 3: ${plan.tp3:,.2f}\n"
        f"Stop Loss: ${plan.stop_loss:,.2f}\n"
        f"Risk/Reward: 1:{plan.rr:.2f}\n\n"
        f"📊 CONFIDENCE ENGINE\n"
        f"Monte Carlo (300): {monte_carlo_prob:.1f}%\n"
        f"Historical hit-rate: {historical_hit_rate:.1f}%\n"
        f"ML model: {ml_verdict} ({ml_confidence:.2f}%)\n"
        f"Blended confidence: {blended_confidence:.1f}%\n\n"
        f"🤖 AI NOTE\n"
        f"{summary[:350]}\n\n"
        f"✅ VERDICT: {verdict}\n"
        f"{WARNING_LINE}"
    )


async def _run_strict_pipeline(
    context: ContextTypes.DEFAULT_TYPE,
    user_text: str,
    image_path: str | None = None,
) -> str:
    prompt = _normalize_user_prompt(user_text)
    ai = await analyze_chart(user_text=prompt, image_path=image_path)

    market_price = await context.bot_data["services"].price_watcher.fetch_price()
    side = _extract_side_from_text(user_text, str(ai.get("bias", "long")).lower())
    entry_price = _derive_entry_price(user_text=user_text, ai_payload=ai, market_price=market_price, side=side)
    pattern = str(ai.get("pattern", "ai-derived"))
    template_hint = str(ai.get("pattern_template", "")).strip()
    template = resolve_template(template_hint or pattern)
    levels = ai.get("key_levels", [])
    swing_ref = _pick_swing_ref(side=side, entry=entry_price, levels=levels if isinstance(levels, list) else [])

    if side == "long":
        plan = build_trade_plan(
            pattern=template.display_name,
            side=side,
            entry=entry_price,
            swing_low=swing_ref,
            swing_high=entry_price + 10,
            stop_multiplier=template.stop_multiplier,
            tp_multipliers=template.tp_multipliers,
        )
    else:
        plan = build_trade_plan(
            pattern=template.display_name,
            side=side,
            entry=entry_price,
            swing_low=entry_price - 10,
            swing_high=swing_ref,
            stop_multiplier=template.stop_multiplier,
            tp_multipliers=template.tp_multipliers,
        )

    candles = await context.bot_data["services"].price_watcher.fetch_recent_candles(limit=200)
    volatility = _volatility_from_candles(candles)
    mc = run_monte_carlo(entry=plan.entry, tp=plan.tp1, sl=plan.stop_loss, volatility=volatility, simulations=300)
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
    historical_hit_rate, historical_samples = _get_contextual_historical_metrics(
        pattern_name=template.key,
        side=side,
        volatility=volatility,
    )
    blended_confidence = _blend_confidence(
        historical_hit_rate=historical_hit_rate,
        monte_carlo_prob=mc.hit_tp_probability,
        ml_confidence=float(ml["confidence"]),
        historical_samples=historical_samples,
    )

    return _format_analysis_text(
        plan=plan,
        market_price=market_price,
        monte_carlo_prob=mc.hit_tp_probability,
        historical_hit_rate=historical_hit_rate,
        blended_confidence=blended_confidence,
        ml_verdict=str(ml["verdict"]),
        ml_confidence=float(ml["confidence"]),
        summary=str(ai.get("summary", "")),
    )


def _format_levels() -> str:
    levels = list_active_levels()
    if not levels:
        return "📭 No active levels yet. Add one with /addlevel 84200 box_top"
    lines = ["📌 WATCHED LEVELS"]
    lines.extend(f"#{lvl.id}  ${lvl.price:,.2f}  ({lvl.label or 'unnamed'})" for lvl in levels)
    lines.append(WARNING_LINE)
    return "\n".join(lines)


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "🚀 CRL Bot is online and ready.\n"
        "Send natural-language ideas or upload a chart image with a caption.\n"
        "⚡ Quick commands: /tradeidea /analyze /patterns /model /price /help\n"
        + WARNING_LINE
    )
    await update.effective_message.reply_text(text)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "📘 BEGINNER GUIDE\n"
        "1) Send chart image + caption: I want to buy near this breakout\n"
        "2) Or use text only: /tradeidea i want to buy at current price, analyze market\n"
        "3) Bot auto-detects pattern, targets, stop loss, and confidence\n"
        "4) Use /patterns to view learned hit-rates\n"
        "5) Use /log box long 84200 WIN TP2 after trade result\n\n"
        + WARNING_LINE
    )
    await update.effective_message.reply_text(text)


async def price_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    price = await context.bot_data["services"].price_watcher.fetch_price()
    await update.effective_message.reply_text(f"💵 BTCUSD: ${price:,.2f}\n{WARNING_LINE}")


async def levels_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(_format_levels())


async def addlevel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 1:
        await update.effective_message.reply_text("ℹ️ Usage: /addlevel <price> [label]")
        return
    try:
        price = float(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("❌ Price must be a number.")
        return

    label = " ".join(context.args[1:]) if len(context.args) > 1 else ""
    level = add_level(price=price, label=label)
    await update.effective_message.reply_text(f"✅ Added level #{level.id} at ${level.price:,.2f} ({label or 'unnamed'})")


async def log_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 4:
        await update.effective_message.reply_text("ℹ️ Usage: /log <pattern> <side> <entry> <WIN|LOSS> [tp_hit]")
        return

    pattern, side, entry_raw, result = context.args[:4]
    tp_hit = context.args[4] if len(context.args) > 4 else "none"

    try:
        entry = float(entry_raw)
    except ValueError:
        await update.effective_message.reply_text("❌ Entry must be numeric.")
        return

    with SessionLocal() as session:
        trade = TradeLog(pattern=pattern, side=side, entry_price=entry, result=result.upper(), tp_hit=tp_hit, rr=2.0)
        session.add(trade)

        stat = session.query(PatternStat).filter_by(pattern=pattern).first()
        if stat is None:
            stat = PatternStat(pattern=pattern, wins=0, losses=0)
            session.add(stat)

        if result.upper() == "WIN":
            stat.wins += 1
        else:
            stat.losses += 1

        session.commit()

    retrained = maybe_retrain_model()
    suffix = " Model retrained." if retrained else ""
    await update.effective_message.reply_text(f"📝 Logged trade for {pattern} ({side.upper()} / {result.upper()}).{suffix}")


async def analyze_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.effective_message.reply_text(
            "ℹ️ Usage:\n"
            "- /analyze <pattern> <long|short> <entry> <swing_ref>\n"
            "- /analyze i want to buy at current price, analyze market"
        )
        return

    # Natural-language mode for non-technical users.
    # Use strict numeric mode only for: /analyze <pattern> <long|short> <entry> <swing_ref>
    strict_mode = False
    if len(context.args) >= 4:
        side_hint = (context.args[1] or "").lower()
        if side_hint in {"long", "short"}:
            try:
                float(context.args[2])
                float(context.args[3])
                strict_mode = True
            except ValueError:
                strict_mode = False

    if not strict_mode:
        try:
            prompt = " ".join(context.args)
            text = await _run_strict_pipeline(context=context, user_text=prompt, image_path=None)
            await update.effective_message.reply_text(text)
        except Exception as exc:
            await update.effective_message.reply_text(f"❌ Natural analysis failed: {exc}")
        return

    pattern = context.args[0]
    side = context.args[1]

    try:
        entry = float(context.args[2])
        swing_ref = float(context.args[3])
    except ValueError:
        await update.effective_message.reply_text("❌ Entry and swing_ref must be numeric.")
        return

    side = side.lower()
    template = resolve_template(pattern)
    if side == "long":
        plan = build_trade_plan(
            pattern=template.display_name,
            side=side,
            entry=entry,
            swing_low=swing_ref,
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
            swing_high=swing_ref,
            stop_multiplier=template.stop_multiplier,
            tp_multipliers=template.tp_multipliers,
        )

    candles = await context.bot_data["services"].price_watcher.fetch_recent_candles(limit=200)
    volatility = _volatility_from_candles(candles)
    mc = run_monte_carlo(entry=plan.entry, tp=plan.tp1, sl=plan.stop_loss, volatility=volatility, simulations=300)
    ml = predict_trade_outcome(
        {
            "pattern": pattern,
            "side": side,
            "session": "unknown",
            "cycle": "unknown",
            "rr": round(plan.rr, 2),
            "volatility": volatility,
        }
    )

    market_price = await context.bot_data["services"].price_watcher.fetch_price()
    historical_hit_rate, historical_samples = _get_contextual_historical_metrics(
        pattern_name=template.key,
        side=side,
        volatility=volatility,
    )
    blended_confidence = _blend_confidence(
        historical_hit_rate=historical_hit_rate,
        monte_carlo_prob=mc.hit_tp_probability,
        ml_confidence=float(ml["confidence"]),
        historical_samples=historical_samples,
    )
    text = _format_analysis_text(
        plan=plan,
        market_price=market_price,
        monte_carlo_prob=mc.hit_tp_probability,
        historical_hit_rate=historical_hit_rate,
        blended_confidence=blended_confidence,
        ml_verdict=str(ml["verdict"]),
        ml_confidence=float(ml["confidence"]),
        summary="Manual analysis command.",
    )
    await update.effective_message.reply_text(text)


async def tradeidea_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.effective_message.reply_text("ℹ️ Usage: /tradeidea <your setup text, e.g. buying at 84200 on box breakout>")
        return

    prompt = " ".join(context.args)
    try:
        text = await _run_strict_pipeline(context=context, user_text=prompt, image_path=None)
        await update.effective_message.reply_text(text)
    except Exception as exc:
        await update.effective_message.reply_text(f"❌ Trade idea analysis failed: {exc}")


async def photo_analysis_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.photo:
        return

    caption = update.message.caption or ""
    temp_file_path: Path | None = None
    try:
        file_obj = await update.message.photo[-1].get_file()
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            temp_file_path = Path(tmp.name)

        await file_obj.download_to_drive(custom_path=str(temp_file_path))
        text = await _run_strict_pipeline(
            context=context,
            user_text=caption or "I want to trade BTC based on this chart. Analyze and give entry, targets, and stop loss.",
            image_path=str(temp_file_path),
        )
        await update.effective_message.reply_text(text)
    except Exception as exc:
        await update.effective_message.reply_text(f"❌ Image analysis failed: {exc}")
    finally:
        if temp_file_path and temp_file_path.exists():
            temp_file_path.unlink(missing_ok=True)


async def model_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = describe_model_state()
    with SessionLocal() as session:
        top = session.query(PatternStat).order_by((PatternStat.wins + PatternStat.losses).desc()).limit(5).all()

    lines = [
        "🧪 CRL INTERNAL STATE",
        f"Trained model file: {'yes' if state['has_trained_model'] else 'no'}",
        f"Fallback profile: {'yes' if state['has_fallback'] else 'no'}",
        f"Trade samples: {state['samples']}",
        f"Fallback win rate: {state['fallback_win_rate']:.2f}%",
        "Top patterns:",
    ]
    if not top:
        lines.append("- none yet")
    else:
        for row in top:
            samples = row.wins + row.losses
            wr = (row.wins / samples) * 100 if samples else 0.0
            lines.append(f"- {row.pattern}: {row.wins}W/{row.losses}L ({wr:.1f}%)")

    lines.append(WARNING_LINE)
    await update.effective_message.reply_text("\n".join(lines))


async def patterns_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        stats = await _fetch_pattern_stats_from_api()
    except Exception:
        stats = _fallback_pattern_stats()

    if not stats:
        await update.effective_message.reply_text("📭 No pattern stats available yet.")
        return

    ranked = sorted(stats, key=lambda s: float(s.get("samples", 0)), reverse=True)[:10]
    lines = ["📈 LIVE PATTERN STATS"]
    for row in ranked:
        lines.append(
            f"- {row.get('pattern', 'unknown')}: "
            f"{int(row.get('wins', 0))}W/{int(row.get('losses', 0))}L "
            f"({float(row.get('win_rate', 0.0)):.1f}%)"
        )
    lines.append(WARNING_LINE)
    await update.effective_message.reply_text("\n".join(lines))


async def natural_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    raw = update.message.text.strip()
    if raw.startswith("/"):
        return

    try:
        text = await _run_strict_pipeline(context=context, user_text=raw, image_path=None)
        await update.effective_message.reply_text(text)
    except Exception as exc:
        await update.effective_message.reply_text(f"❌ Text analysis failed: {exc}")


def build_handlers() -> list[BaseHandler]:
    return [
        CommandHandler("start", start_cmd),
        CommandHandler("help", help_cmd),
        CommandHandler("price", price_cmd),
        CommandHandler("levels", levels_cmd),
        CommandHandler("addlevel", addlevel_cmd),
        CommandHandler("log", log_cmd),
        CommandHandler("analyze", analyze_cmd),
        CommandHandler("tradeidea", tradeidea_cmd),
        CommandHandler("model", model_cmd),
        CommandHandler("patterns", patterns_cmd),
        MessageHandler(filters.PHOTO, photo_analysis_handler),
        MessageHandler(filters.TEXT & (~filters.COMMAND), natural_text_handler),
    ]
