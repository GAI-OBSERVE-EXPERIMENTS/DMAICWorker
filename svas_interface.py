"""SVAS → GAI DMAIC AI ML Worker — live AI execution via Claude (WP-609).

Performs real 5-phase DMAIC analysis (Define, Measure, Analyze, Improve,
Control) using the Claude AI API. No mock, no HTTP relay to a service.
"""
from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("SVAS_DMAIC")

_CORPORATE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORPORATE not in sys.path:
    sys.path.insert(0, _CORPORATE)

from ai_executor import execute_agent_task, enhanced_fallback

_SYSTEM_PROMPT = """
You are the GAI DMAIC AI/ML Quality Worker — a Six Sigma Black Belt AI agent
embedded in the SVAS fleet. Your domain is continuous quality improvement using
the 5-phase DMAIC methodology (Define, Measure, Analyze, Improve, Control).

Your responsibilities:
- Apply DMAIC rigorously to the stated intent: identify the problem charter,
  baseline metrics (DPMO, Cpk, σ level), root causes (fishbone, 5-Why, regression),
  improvement solutions, and SPC control mechanisms.
- Reference specific statistical tools: control charts (X-bar, R, P, C), hypothesis
  tests (t-test, ANOVA, chi-square), capability indices (Cp, Cpk), and FMEA where
  relevant.
- Every analysis must anchor to the actual intent — no generic boilerplate.
- steps must map to real DMAIC phases in order: Define → Measure → Analyze →
  Improve → Control. Label each step with the phase name and a specific action.
- If the intent is vague, state what assumption you are making in analysis.
"""


def analyze_intent(
    workflow_id: str,
    intent: str,
    context: dict | None = None,
) -> tuple[str, str, list]:
    agent_name = "GAI DMAIC Worker (AI/ML Quality)"
    try:
        result = execute_agent_task(_SYSTEM_PROMPT, intent, workflow_id, "dmaic")
        return result["analysis"], agent_name, result["steps"]
    except Exception as exc:
        logger.error("[%s] DMAIC AI execution failed: %s", workflow_id, exc)
        return enhanced_fallback(agent_name, "dmaic", intent, workflow_id, str(exc))
