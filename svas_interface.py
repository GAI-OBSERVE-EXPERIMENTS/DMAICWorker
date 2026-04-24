"""SVAS → GAI DMAIC AI ML Worker bridge (WP-609).

GAI DMAIC Worker orchestrates the 5-phase DMAIC cycle (Define, Measure,
Analyze, Improve, Control) for AI/ML projects. Each phase is a gated
workflow with quality gates and human-in-the-loop approval at Control.

Flow:
  1. TCP probe  → is DMAIC API running?
  2. GET /health → confirm API is healthy
  3. POST /api/v1/dmaic/submit-phase → submit DMAIC phase intent
  4. Deterministic mock fallback when API offline

Configuration (env vars):
  DMAIC_API_URL  — default http://localhost:8010
  DMAIC_TIMEOUT  — HTTP timeout in seconds, default 5
"""
from __future__ import annotations

import json
import logging
import os
import socket
from urllib.error import URLError
from urllib.request import Request, urlopen

logger = logging.getLogger("SVAS_DMAIC_Bridge")

_DMAIC_BASE = os.getenv("DMAIC_API_URL", "http://localhost:8010").rstrip("/")
_TIMEOUT    = float(os.getenv("DMAIC_TIMEOUT", "5"))


def _is_dmaic_reachable() -> bool:
    try:
        url = _DMAIC_BASE.replace("http://", "").replace("https://", "")
        host, _, port_str = url.partition(":")
        port = int(port_str) if port_str else 80
        with socket.create_connection((host, port), timeout=1):
            return True
    except Exception:
        return False


def _is_dmaic_healthy() -> bool:
    try:
        req = Request(f"{_DMAIC_BASE}/health", method="GET")
        with urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
            return data.get("status") in ("healthy", "ok", "OK", "operational")
    except Exception:
        return False


def _submit_phase(intent: str, workflow_id: str) -> dict | None:
    """POST /api/v1/dmaic/submit-phase and return parsed JSON, or None on error."""
    try:
        body = json.dumps({
            "intent":      intent,
            "workflow_id": f"svas-{workflow_id}",
        }).encode()
        req = Request(
            f"{_DMAIC_BASE}/api/v1/dmaic/submit-phase",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:
        logger.warning("DMAIC phase submission failed: %s", exc)
        return None


def _response_to_svas(
    response: dict,
    intent: str,
    workflow_id: str,
) -> tuple[str, str, list]:
    phase_id  = response.get("phase_id") or response.get("id") or workflow_id
    status    = response.get("status", "submitted")
    temporal_up = status in ("submitted", "running", "queued", "accepted")

    analysis = (
        f"GAI DMAIC Worker connected (phase_id={phase_id}, status={status}):\n"
        f"  Intent routed to DMAIC orchestrator — 5-phase quality gate engaged."
    )

    if temporal_up:
        steps = [
            {"id": "s1", "label": "DMAIC: Define — Charter scope and goals"},
            {"id": "s2", "label": "DMAIC: Measure — Baseline metrics collection"},
            {"id": "s3", "label": "DMAIC: Analyze — Root cause & statistical tests"},
            {"id": "s4", "label": "DMAIC: Improve — Solution design and pilot"},
            {"id": "s5", "label": "DMAIC: Control — SPC monitoring + HITL sign-off"},
        ]
    else:
        steps = [
            {"id": "s1", "label": "DMAIC: Define phase (local)"},
            {"id": "s2", "label": "DMAIC: Measure + Analyze (local)"},
            {"id": "s3", "label": "DMAIC: Control gate (local)"},
        ]

    return analysis, "GAI DMAIC Worker (AI/ML Quality)", steps


def _mock_response(
    intent: str,
    workflow_id: str,
    reason: str,
) -> tuple[str, str, list]:
    logger.info("[%s] DMAIC bridge using mock fallback: %s", workflow_id, reason)
    analysis = (
        f"GAI DMAIC Worker (offline — {reason}):\n"
        f"  Intent: {intent[:80]}{'...' if len(intent) > 80 else ''}\n"
        f"  Running DMAIC phases in local simulation mode."
    )
    steps = [
        {"id": "s1", "label": "DMAIC: Define phase (local)"},
        {"id": "s2", "label": "DMAIC: Measure + Analyze (local)"},
        {"id": "s3", "label": "DMAIC: Control gate (local)"},
    ]
    return analysis, "GAI DMAIC Worker (AI/ML Quality)", steps


def analyze_intent(
    workflow_id: str,
    intent: str,
    context: dict | None = None,
) -> tuple[str, str, list]:
    """
    Primary SVAS entry-point for GAI DMAIC Worker persona.

    Submits an AI/ML quality improvement intent through the 5-phase
    DMAIC orchestrator. Falls back to local simulation if API offline.
    """
    if not _is_dmaic_reachable():
        return _mock_response(intent, workflow_id, f"DMAIC not reachable at {_DMAIC_BASE}")

    if not _is_dmaic_healthy():
        return _mock_response(intent, workflow_id, "DMAIC /health returned unhealthy")

    response = _submit_phase(intent, workflow_id)
    if response is None:
        return _mock_response(intent, workflow_id, "submit-phase call failed")

    return _response_to_svas(response, intent, workflow_id)
