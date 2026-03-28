from __future__ import annotations

import asyncio
import base64
import json
import re
from pathlib import Path
from typing import Any

import httpx

from bot.config import settings


def _load_rules() -> str:
    rules_file = Path("data/crl_brain.txt")
    if not rules_file.exists():
        return "Use strict risk management and candle close confirmation."
    return rules_file.read_text(encoding="utf-8")


def _fallback_analysis(user_text: str, reason: str) -> dict[str, Any]:
    source = (user_text or "").lower()
    side = "short" if any(k in source for k in ["short", "sell", "selling"]) else "long"

    if any(k in source for k in ["triangle", "wedge"]):
        template = "triangle"
        pattern = "Triangle breakout"
    elif any(k in source for k in ["channel", "pullback"]):
        template = "channel"
        pattern = "Channel continuation"
    elif any(k in source for k in ["flag", "pennant"]):
        template = "flag"
        pattern = "Flag continuation"
    elif any(k in source for k in ["double top", "double bottom", "head and shoulders", "reversal"]):
        template = "reversal"
        pattern = "Reversal setup"
    elif any(k in source for k in ["breakout", "range", "box", "consolidation"]):
        template = "box"
        pattern = "Range/box breakout"
    else:
        template = "generic"
        pattern = "Generic market structure"

    levels = []
    for token in re.findall(r"\d{4,8}(?:\.\d+)?", source):
        try:
            levels.append(float(token))
        except Exception:
            continue

    return {
        "pattern": pattern,
        "pattern_template": template,
        "bias": side,
        "key_levels": levels[:5],
        "entry_hint": "wait for 5m close confirmation",
        "summary": f"Fallback local analysis used ({reason}). Pattern and bias inferred from your text.",
    }


def _parse_structured_reply(reply: Any) -> dict[str, Any]:
    if isinstance(reply, list):
        reply = "\n".join(part.get("text", "") for part in reply if isinstance(part, dict))

    parsed: dict[str, Any] = {}
    if isinstance(reply, str):
        try:
            parsed = json.loads(reply)
        except Exception:
            match = re.search(r"\{[\s\S]*\}", reply)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                except Exception:
                    parsed = {}

    pattern = str(parsed.get("pattern", "ai-derived"))
    bias = str(parsed.get("bias", "neutral")).lower()
    key_levels = parsed.get("key_levels", [])
    if not isinstance(key_levels, list):
        key_levels = []
    numeric_levels = []
    for item in key_levels:
        try:
            numeric_levels.append(float(item))
        except Exception:
            continue

    summary = parsed.get("summary") if isinstance(parsed.get("summary"), str) else str(reply)
    return {
        "pattern": pattern,
        "pattern_template": str(parsed.get("pattern_template", "generic")).lower(),
        "bias": bias,
        "key_levels": numeric_levels,
        "entry_hint": parsed.get("entry_hint", "wait for 5m close confirmation"),
        "summary": summary,
    }


async def _analyze_with_gemini(user_text: str, image_path: str | None = None, api_key: str | None = None) -> dict[str, Any]:
    if not api_key:
        api_key = settings.gemini_api_key
    if not api_key:
        api_key = settings.gemini_api_key_backup
    if not api_key:
        return _fallback_analysis(user_text, "Gemini keys missing")

    schema_instruction = (
        "Return strict JSON with keys: pattern, pattern_template, bias, key_levels, entry_hint, summary. "
        "pattern_template must be one of box, triangle, channel, flag, reversal, generic."
    )
    parts: list[dict[str, Any]] = [{"text": f"Rules:\n{_load_rules()}\n\nUser input: {user_text}\n\n{schema_instruction}"}]
    if image_path:
        encoded = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
        parts.append({"inline_data": {"mime_type": "image/png", "data": encoded}})

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1200},
    }

    model_candidates = [
        settings.gemini_model,
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-1.5-flash-latest",
    ]

    last_exc: Exception | None = None
    async with httpx.AsyncClient(timeout=30.0) as client:
        for model_name in model_candidates:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
                f"?key={api_key}"
            )
            try:
                response = await client.post(url, json=payload)
                
                if response.status_code == 200:
                    data = response.json()
                    break
                elif response.status_code == 429:
                    # Quota exceeded - move to next service (OpenRouter)
                    last_exc = Exception(f"Gemini: HTTP 429 (quota exceeded)")
                    continue
                elif response.status_code == 404:
                    # Model doesn't exist, try next model
                    last_exc = Exception(f"Gemini model {model_name}: HTTP 404")
                    continue
                else:
                    # Other error
                    last_exc = Exception(f"Gemini: HTTP {response.status_code}")
                    continue
            except Exception as exc:
                last_exc = exc
                continue
        else:
            # All models tried, raise error
            raise RuntimeError(f"Gemini request failed for all models: {last_exc}")

    text = ""
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        text = json.dumps(data)

    return _parse_structured_reply(text)


async def analyze_chart(user_text: str, image_path: str | None = None) -> dict[str, Any]:
    if not settings.openrouter_api_key:
        return _fallback_analysis(user_text, "OpenRouter key missing")

    schema_instruction = (
        "Return strict JSON with keys: pattern, pattern_template, bias, key_levels, entry_hint, summary. "
        "pattern is the detected setup name. pattern_template must be one of box, triangle, channel, flag, reversal, generic. "
        "bias must be long/short/neutral. key_levels must be an array of numbers."
    )
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": f"Rules:\n{_load_rules()}\n\nUser input: {user_text}\n\n{schema_instruction}",
        }
    ]
    if image_path:
        encoded = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{encoded}"},
            }
        )

    payload = {
        "model": settings.openrouter_model,
        "messages": [
            {
                "role": "user",
                "content": content,
            }
        ],
        "max_tokens": 1200,
    }

    # Try primary and backup OpenRouter keys
    for api_key in [settings.openrouter_api_key, settings.openrouter_api_key_backup]:
        if not api_key:
            continue
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        max_retries = 3
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
                    
                    if response.status_code == 200:
                        data = response.json()
                        reply = data["choices"][0]["message"]["content"]
                        return _parse_structured_reply(reply)
                    elif response.status_code == 429:
                        # Rate limited - wait and retry same key
                        if attempt < max_retries - 1:
                            wait_time = 2 ** attempt
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            break  # Move to next key
                    elif response.status_code in (402, 401):
                        # Insufficient credits or auth error - try next key
                        break
                    else:
                        # Other error - try next key
                        break
            except httpx.HTTPStatusError as exc:
                if exc.response is not None and exc.response.status_code == 429:
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt
                        await asyncio.sleep(wait_time)
                        continue
                break
            except Exception:
                break
    
    # Both OpenRouter keys failed or exhausted, try Gemini keys
    for gemini_key in [settings.gemini_api_key, settings.gemini_api_key_backup]:
        if not gemini_key:
            continue
        try:
            return await _analyze_with_gemini(user_text=user_text, image_path=image_path, api_key=gemini_key)
        except Exception:
            continue
    
    # All keys failed
    return _fallback_analysis(user_text, "All API keys exhausted or invalid")
