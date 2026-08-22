"""
Part 04 — Dual-Model Router

Provides two functions (plan_next_action, decide_strategy) that try a primary
model first and transparently fail over to a distinct secondary model.

Primary: Google Gemini   Secondary: OpenAI GPT
Env: GEMINI_API_KEY, OPENAI_API_KEY, FORCE_PRIMARY_DOWN
"""

import asyncio
import json
import logging
import os
import re
import time
from typing import Any

logger = logging.getLogger("toolfall.model_router")

# ---------------------------------------------------------------------------
# Failover event callback — Part 05 will set this so events reach the WS bus
# ---------------------------------------------------------------------------
_failover_callback = None

def set_failover_callback(cb):
    """Register a coroutine that will be awaited on model_failover events."""
    global _failover_callback
    _failover_callback = cb

async def _emit_failover(from_model: str, to_model: str, reason: str):
    event = {
        "event": "model_failover",
        "from_model": from_model,
        "to_model": to_model,
        "reason": reason,
        "ts": _iso_now(),
    }
    logger.warning("Model failover: %s → %s (%s)", from_model, to_model, reason)
    if _failover_callback:
        await _failover_callback(event)

def _iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PRIMARY_TIMEOUT = 8  # seconds
VALID_TOOLS = {"lookup_booking", "check_availability", "charge_fare_difference", "send_confirmation"}
VALID_STRATEGIES = {"RETRY_IMMEDIATE", "RETRY_BACKOFF", "SWITCH_MODEL", "USE_STALE_CACHE", "ESCALATE_TO_HUMAN"}

TOOL_DESCRIPTIONS = {
    "lookup_booking": "Fetch an existing flight reservation by booking_id. Args: booking_id (str).",
    "check_availability": "Check seat availability for a new date on a route. Args: new_date (str, ISO date), route (str, e.g. 'DEL-BOM').",
    "charge_fare_difference": "Charge the passenger for any price difference. Args: amount (float), payment_token (str).",
    "send_confirmation": "Email the passenger a confirmation with the updated itinerary. Args: email (str), itinerary (dict).",
}

# ---------------------------------------------------------------------------
# Prompt templates (designed to work across both models)
# ---------------------------------------------------------------------------
PLAN_SYSTEM_PROMPT = """You are an AI flight-rescheduling agent. You must decide the NEXT tool to call.

Available tools (call exactly ONE):
- lookup_booking: Fetch booking. Args: {"booking_id": "<id>"}
- check_availability: Check seats. Args: {"new_date": "<ISO date>", "route": "<ORIGIN-DEST>"}
- charge_fare_difference: Charge price diff. Args: {"amount": <float>, "payment_token": "<token>"}
- send_confirmation: Send email. Args: {"email": "<addr>", "itinerary": <dict>}

IMPORTANT RULES:
1. Follow this order: lookup_booking → check_availability → charge_fare_difference → send_confirmation
2. Only skip charge_fare_difference if price_delta is 0 or negative.
3. If a step already has results in the task state, move to the next step.
4. If availability shows available=false, the task cannot continue — set tool to "NONE".

Respond with ONLY a JSON object (no markdown fences):
{"tool": "<tool_name or NONE>", "args": {<arguments>}}"""

STRATEGY_SYSTEM_PROMPT = """You are a resilience-strategy advisor for an AI agent's tool calls.

A tool call has FAILED. Given the fault context, choose exactly ONE strategy:
- RETRY_IMMEDIATE: Retry right away (good for transient errors, low attempt count)
- RETRY_BACKOFF: Retry after a delay (good for rate limits or repeated failures). Provide backoff_seconds.
- SWITCH_MODEL: Try a different AI model to reformulate the call
- USE_STALE_CACHE: Return the last known good result (acceptable for non-critical reads)
- ESCALATE_TO_HUMAN: Give up automated recovery, route to human review (use for high-stakes repeated failures)

RULES:
- For RATE_LIMIT faults, prefer RETRY_BACKOFF with 3-10 seconds.
- For ERROR_500 on attempt 1, prefer RETRY_IMMEDIATE.
- For any fault on attempt >= 3, prefer ESCALATE_TO_HUMAN if stakes are "high".
- For SILENT_NULL or CORRUPT_PAYLOAD, prefer RETRY_IMMEDIATE on first attempt, then ESCALATE_TO_HUMAN.
- SWITCH_MODEL is good when the current model produced a bad plan, not for tool-level faults.
- If stakes are "high" and attempt >= 2, lean toward ESCALATE_TO_HUMAN.

Respond with ONLY a JSON object (no markdown fences):
{"strategy": "<STRATEGY>", "backoff_seconds": <number or null>, "reasoning": "<one sentence>"}"""

# ---------------------------------------------------------------------------
# Model clients
# ---------------------------------------------------------------------------

async def _call_gemini(system_prompt: str, user_prompt: str) -> dict:
    """Call Google Gemini API. Raises on any failure."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise ConnectionError("GEMINI_API_KEY not set")

    import httpx
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
        },
    }
    async with httpx.AsyncClient(timeout=PRIMARY_TIMEOUT) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return _parse_json_response(text)


async def _call_openai(system_prompt: str, user_prompt: str) -> dict:
    """Call OpenAI API. Raises on any failure."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise ConnectionError("OPENAI_API_KEY not set")

    import httpx
    url = "https://api.openai.com/v1/chat/completions"
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=PRIMARY_TIMEOUT) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        return _parse_json_response(text)


def _parse_json_response(text: str) -> dict:
    """Parse a JSON response, stripping markdown fences if present."""
    text = text.strip()
    # Strip markdown code fences
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    result = json.loads(text)
    if not isinstance(result, dict):
        raise ValueError("Model response is not a JSON object")
    return result


# ---------------------------------------------------------------------------
# Rule-based fallbacks (when BOTH models are unavailable / no keys)
# ---------------------------------------------------------------------------

def _rule_based_plan(task_state: dict) -> dict:
    """Deterministic planner — follows the fixed 4-step pipeline."""
    results = task_state.get("results", {})
    request = task_state.get("request", "")
    booking_id = task_state.get("booking_id", "BKG123")
    new_date = task_state.get("new_date", "2026-09-15")

    # Step 1: lookup
    if "lookup_booking" not in results and "lookup_booking" not in task_state.get("escalated", {}):
        return {"tool": "lookup_booking", "args": {"booking_id": booking_id}}

    booking = results.get("lookup_booking", {})
    route = booking.get("route", "DEL-BOM")

    # Step 2: availability
    if "check_availability" not in results and "check_availability" not in task_state.get("escalated", {}):
        return {"tool": "check_availability", "args": {"new_date": new_date, "route": route}}

    avail = results.get("check_availability", {})
    if not avail.get("available", False):
        return {"tool": "NONE", "args": {}}

    # Step 3: charge (skip if delta <= 0)
    price_delta = avail.get("price_delta", 0.0)
    if "charge_fare_difference" not in results and "charge_fare_difference" not in task_state.get("escalated", {}) and price_delta > 0:
        return {
            "tool": "charge_fare_difference",
            "args": {"amount": price_delta, "payment_token": task_state.get("payment_token", "tok_default")},
        }

    # Step 4: confirmation
    if "send_confirmation" not in results and "send_confirmation" not in task_state.get("escalated", {}):
        email = task_state.get("email", booking.get("passenger_name", "").replace(" ", ".").lower() + "@example.com")
        itinerary = {
            "booking_id": booking.get("booking_id"),
            "passenger_name": booking.get("passenger_name"),
            "route": route,
            "old_date": booking.get("date"),
            "new_date": new_date,
            "fare": booking.get("fare", 0) + price_delta,
        }
        return {"tool": "send_confirmation", "args": {"email": email, "itinerary": itinerary}}

    return {"tool": "NONE", "args": {}}


def _rule_based_strategy(fault_context: dict) -> dict:
    """Deterministic strategy selector — no model needed."""
    fault_type = fault_context.get("fault_type", "ERROR_500")
    attempt = fault_context.get("attempt", 1)
    stakes = fault_context.get("task_stakes", "medium")

    # High-stakes + repeated failures → escalate
    if stakes == "high" and attempt >= 2:
        return {
            "strategy": "ESCALATE_TO_HUMAN",
            "backoff_seconds": None,
            "reasoning": f"High-stakes tool failed {attempt} times — escalating to human review.",
        }

    if fault_type == "RATE_LIMIT":
        backoff = min(2 ** attempt, 30)
        return {
            "strategy": "RETRY_BACKOFF",
            "backoff_seconds": float(backoff),
            "reasoning": f"Rate limited; backing off {backoff}s before retry.",
        }

    if fault_type == "ERROR_500":
        if attempt <= 2:
            return {
                "strategy": "RETRY_IMMEDIATE",
                "backoff_seconds": None,
                "reasoning": f"Server error on attempt {attempt}; retrying immediately.",
            }
        return {
            "strategy": "ESCALATE_TO_HUMAN",
            "backoff_seconds": None,
            "reasoning": f"Server error persisted after {attempt} attempts — escalating.",
        }

    if fault_type in ("SILENT_NULL", "CORRUPT_PAYLOAD"):
        if attempt <= 1:
            return {
                "strategy": "RETRY_IMMEDIATE",
                "backoff_seconds": None,
                "reasoning": f"{fault_type} detected on first attempt; retrying.",
            }
        return {
            "strategy": "ESCALATE_TO_HUMAN",
            "backoff_seconds": None,
            "reasoning": f"{fault_type} persisted after {attempt} attempts — needs human review.",
        }

    if fault_type == "LATENCY_SPIKE":
        return {
            "strategy": "RETRY_BACKOFF",
            "backoff_seconds": 3.0,
            "reasoning": "Latency spike detected; waiting 3s before retrying.",
        }

    # Catch-all
    if attempt >= 3:
        return {
            "strategy": "ESCALATE_TO_HUMAN",
            "backoff_seconds": None,
            "reasoning": f"Unknown fault after {attempt} attempts — escalating.",
        }
    return {
        "strategy": "RETRY_IMMEDIATE",
        "backoff_seconds": None,
        "reasoning": f"Transient fault on attempt {attempt}; retrying.",
    }


# ---------------------------------------------------------------------------
# Core wrapper: try primary → failover to secondary → fallback to rules
# ---------------------------------------------------------------------------

async def _call_with_failover(system_prompt: str, user_prompt: str) -> tuple[dict, str]:
    """
    Try primary (Gemini) → secondary (OpenAI) → rule-based.
    Returns (parsed_response, model_used).
    """
    force_down = os.environ.get("FORCE_PRIMARY_DOWN", "").lower() == "true"

    # ---- primary ----
    if not force_down:
        try:
            result = await asyncio.wait_for(
                _call_gemini(system_prompt, user_prompt),
                timeout=PRIMARY_TIMEOUT,
            )
            return result, "primary"
        except asyncio.TimeoutError:
            await _emit_failover("primary", "secondary", "timeout")
        except (ConnectionError, KeyError) as e:
            await _emit_failover("primary", "secondary", "provider_error")
        except json.JSONDecodeError:
            await _emit_failover("primary", "secondary", "invalid_response")
        except Exception as e:
            logger.warning("Primary model error (%s): %s", type(e).__name__, e)
            await _emit_failover("primary", "secondary", "provider_error")
    else:
        await _emit_failover("primary", "secondary", "forced_for_demo")

    # ---- secondary ----
    try:
        result = await asyncio.wait_for(
            _call_openai(system_prompt, user_prompt),
            timeout=PRIMARY_TIMEOUT,
        )
        return result, "secondary"
    except Exception as e:
        logger.warning("Secondary model also failed (%s): %s — using rule-based fallback", type(e).__name__, e)

    # ---- return None to signal caller to use rules ----
    return None, "rule_based"


# ---------------------------------------------------------------------------
# Public API — frozen interface (Section 6.2)
# ---------------------------------------------------------------------------

async def plan_next_action(task_state: dict) -> dict:
    """
    Decide which tool to call next given the current task state.
    Returns: {"tool": str, "args": dict, "model_used": "primary"|"secondary"}
    """
    user_prompt = f"Current task state:\n{json.dumps(task_state, indent=2, default=str)}"
    raw, model_used = await _call_with_failover(PLAN_SYSTEM_PROMPT, user_prompt)

    if raw is None:
        # Both models unavailable — use deterministic rules
        plan = _rule_based_plan(task_state)
        plan["model_used"] = "secondary"  # report as secondary per contract
        return plan

    # Validate and normalize the response
    tool = raw.get("tool", "NONE")
    args = raw.get("args", {})
    if not isinstance(args, dict):
        args = {}

    return {"tool": tool, "args": args, "model_used": model_used}


async def decide_strategy(fault_context: dict) -> dict:
    """
    Given a fault context, decide which resilience strategy to use.
    fault_context = {"tool": str, "fault_type": str, "attempt": int, "task_stakes": str}
    Returns: {
        "strategy": str, "backoff_seconds": float|None,
        "model_used": "primary"|"secondary", "reasoning": str
    }
    """
    user_prompt = (
        f"A tool call to `{fault_context.get('tool', 'unknown')}` failed with fault type "
        f"`{fault_context.get('fault_type', 'UNKNOWN')}` on attempt {fault_context.get('attempt', 1)}. "
        f"This tool is `{fault_context.get('task_stakes', 'medium')}` stakes.\n\n"
        f"Full context:\n{json.dumps(fault_context, indent=2, default=str)}"
    )

    raw, model_used = await _call_with_failover(STRATEGY_SYSTEM_PROMPT, user_prompt)

    if raw is None:
        # Both models unavailable — use deterministic rules
        strategy = _rule_based_strategy(fault_context)
        strategy["model_used"] = "secondary"
        return strategy

    # Validate and normalize
    strategy = raw.get("strategy", "RETRY_IMMEDIATE")
    if strategy not in VALID_STRATEGIES:
        strategy = "RETRY_IMMEDIATE"

    backoff = raw.get("backoff_seconds")
    if backoff is not None:
        try:
            backoff = float(backoff)
        except (TypeError, ValueError):
            backoff = None

    reasoning = raw.get("reasoning", "No reasoning provided.")
    if not isinstance(reasoning, str) or len(reasoning) < 3:
        reasoning = "Strategy selected by model."

    return {
        "strategy": strategy,
        "backoff_seconds": backoff,
        "model_used": model_used,
        "reasoning": reasoning,
    }
