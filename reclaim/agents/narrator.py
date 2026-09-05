"""
LLM Narrator for RECLAIM.

Additive-only narration layer that runs AFTER a case's decision is finalized.
Never feeds back into the decision loop — purely generates human-readable
messages for customer communication and human-review briefings.

Uses Groq (Llama 3) as the LLM provider. Falls back to hardcoded templates
on any failure (missing key, timeout, rate limit) so the demo never depends
on a live network call succeeding.
"""

import os
import json

# Load .env for GROQ_API_KEY
from reclaim.core.razorpay_adapter import load_env
load_env()

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    Groq = None
    GROQ_AVAILABLE = False


# ── Template Fallbacks ──────────────────────────────────────────────────────

def _template_customer_message(case: dict, root_cause: str, action: str) -> str:
    """Hardcoded template fallback for customer messages."""
    amount = case.get("amount", 0)
    case_id = case.get("case_id", "unknown")
    scenario = case.get("scenario", "transaction")

    if action == "reminder_message":
        return (
            f"Hi — we noticed your {scenario.replace('_', ' ')} of ₹{amount:,.2f} "
            f"(ref: {case_id}) didn't go through. "
            f"These issues are usually quick to resolve. "
            f"Please try again at your convenience — we're here to help if anything comes up."
        )
    elif action == "otp_assist_link":
        return (
            f"Hi — your transaction of ₹{amount:,.2f} (ref: {case_id}) "
            f"needs a quick OTP verification to complete. "
            f"We've sent a fresh OTP to your registered number. "
            f"Please complete the verification within the next few minutes."
        )
    return f"Your transaction {case_id} (₹{amount:,.2f}) needs attention. Please check your payment method."


def _template_escalation_briefing(
    case: dict, root_cause: str, confidence: float, reason: str
) -> str:
    """Hardcoded template fallback for escalation briefings."""
    case_id = case.get("case_id", "unknown")
    amount = case.get("amount", 0)
    scenario = case.get("scenario", "transaction")

    return (
        f"ESCALATION BRIEF — {case_id}\n"
        f"Scenario: {scenario.replace('_', ' ').title()} | Amount: ₹{amount:,.2f}\n"
        f"Root Cause: {root_cause.replace('_', ' ').title()}\n"
        f"Confidence: {confidence:.0f} observations (below auto-approval floor)\n"
        f"Reason: {reason}\n"
        f"Recommended: Manual review and customer outreach required."
    )


# ── LLM-Powered Functions ──────────────────────────────────────────────────

_GROQ_MODEL = "qwen/qwen3.8-27b"
_TIMEOUT = 10  # seconds


def _call_groq(system_prompt: str, user_prompt: str) -> str | None:
    """
    Make a single Groq API call. Returns the response text or None on failure.
    """
    if not GROQ_AVAILABLE:
        return None

    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        return None

    try:
        client = Groq(api_key=api_key, timeout=_TIMEOUT)
        response = client.chat.completions.create(
            model=_GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=300,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return None


def draft_customer_message(case: dict, root_cause: str, action: str) -> str:
    """
    Draft a short, specific customer message for reminder_message or otp_assist_link.

    Calls Groq LLM to generate a personalized 2-3 sentence message referencing
    the case context. Falls back to a template on any failure.
    """
    system_prompt = (
        "You are a friendly, professional customer support assistant for an online payment platform. "
        "Draft a short (2-3 sentences), specific customer message. Be warm but concise. "
        "Reference the specific transaction details provided. Do not use markdown formatting. "
        "Do not include subject lines or signatures."
    )

    scenario_desc = case.get("scenario", "transaction").replace("_", " ")
    amount = case.get("amount", 0)
    case_id = case.get("case_id", "unknown")

    extra_context = ""
    if case.get("scenario") == "payment_failure":
        extra_context = f"Decline reason: {case.get('decline_reason', 'unknown')}. "
    elif case.get("scenario") == "checkout_abandonment":
        extra_context = f"Customer stopped at: {case.get('abandonment_step', 'unknown')} step. "

    action_desc = "a gentle payment reminder" if action == "reminder_message" else "an OTP assistance link"

    user_prompt = (
        f"Case: {case_id} | Scenario: {scenario_desc} | Amount: ₹{amount:,.2f} | "
        f"Root cause: {root_cause.replace('_', ' ')} | {extra_context}"
        f"Action type: {action_desc}. "
        f"Draft the customer message now."
    )

    llm_result = _call_groq(system_prompt, user_prompt)
    if llm_result:
        return llm_result

    return _template_customer_message(case, root_cause, action)


def draft_escalation_briefing(
    case: dict, root_cause: str, confidence: float, reason: str
) -> str:
    """
    Draft a short human-readable escalation briefing for whoever picks up the case.

    Calls Groq LLM to generate a concise briefing from the evidence.
    Falls back to a template on any failure.
    """
    system_prompt = (
        "You are an internal AI assistant writing a brief escalation note for a human reviewer "
        "at a payment recovery team. Summarize the case concisely (3-4 sentences). "
        "Include the key facts: what happened, why it was escalated, and what the reviewer should do. "
        "Do not use markdown formatting. Be direct and professional."
    )

    scenario_desc = case.get("scenario", "transaction").replace("_", " ")
    amount = case.get("amount", 0)
    case_id = case.get("case_id", "unknown")

    extra_context = ""
    if case.get("scenario") == "payment_failure":
        extra_context = (
            f"Decline reason: {case.get('decline_reason', 'unknown')}. "
            f"Prior retries: {case.get('retry_count_so_far', 0)}. "
        )
    elif case.get("scenario") == "checkout_abandonment":
        extra_context = (
            f"Abandonment step: {case.get('abandonment_step', 'unknown')}. "
            f"Time since abandonment: {case.get('minutes_since_abandonment', 0)} minutes. "
        )

    user_prompt = (
        f"Case: {case_id} | Scenario: {scenario_desc} | Amount: ₹{amount:,.2f} | "
        f"Root cause: {root_cause.replace('_', ' ')} | {extra_context}"
        f"Confidence: {confidence:.0f} observations | Escalation reason: {reason}. "
        f"Write the escalation briefing now."
    )

    llm_result = _call_groq(system_prompt, user_prompt)
    if llm_result:
        return llm_result

    return _template_escalation_briefing(case, root_cause, confidence, reason)
