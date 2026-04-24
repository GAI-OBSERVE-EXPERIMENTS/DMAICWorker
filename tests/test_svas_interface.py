"""Tests for WP-609 — GAI DMAIC AI ML Worker SVAS bridge (svas_interface.py)."""
import json
import sys
import os
from unittest.mock import MagicMock, patch
from urllib.error import URLError

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import svas_interface as bridge


# ── _mock_response ─────────────────────────────────────────────────────────────

def test_mock_response_returns_tuple():
    analysis, agent, steps = bridge._mock_response("intent", "wf-1", "offline")
    assert isinstance(analysis, str)
    assert agent == "GAI DMAIC Worker (AI/ML Quality)"
    assert len(steps) >= 1


def test_mock_response_includes_reason():
    analysis, _, _ = bridge._mock_response("run dmaic cycle", "wf-2", "not reachable at localhost")
    assert "not reachable at localhost" in analysis


def test_mock_response_truncates_intent():
    long_intent = "D" * 200
    analysis, _, _ = bridge._mock_response(long_intent, "wf-3", "offline")
    assert len(analysis) < 400


def test_mock_response_steps_have_id_and_label():
    _, _, steps = bridge._mock_response("intent", "wf-4", "reason")
    for step in steps:
        assert "id" in step and "label" in step


# ── _response_to_svas ──────────────────────────────────────────────────────────

def test_response_to_svas_temporal_up():
    response = {"status": "submitted", "phase_id": "dmaic-001"}
    analysis, agent, steps = bridge._response_to_svas(response, "improve model drift", "wf-5")
    assert agent == "GAI DMAIC Worker (AI/ML Quality)"
    assert "dmaic-001" in analysis
    assert len(steps) == 5


def test_response_to_svas_temporal_down():
    response = {"status": "error", "phase_id": "dmaic-err"}
    analysis, agent, steps = bridge._response_to_svas(response, "improve model", "wf-6")
    assert len(steps) == 3
    assert all("local" in s["label"].lower() for s in steps)


def test_response_to_svas_agent_name():
    response = {"status": "queued", "phase_id": "x"}
    _, agent, _ = bridge._response_to_svas(response, "intent", "wf-7")
    assert agent == "GAI DMAIC Worker (AI/ML Quality)"


def test_response_to_svas_falls_back_to_workflow_id():
    response = {"status": "submitted"}
    analysis, _, _ = bridge._response_to_svas(response, "intent", "wf-fallback")
    assert "wf-fallback" in analysis


def test_response_to_svas_steps_have_id_label():
    response = {"status": "running", "phase_id": "d1"}
    _, _, steps = bridge._response_to_svas(response, "intent", "wf-8")
    for step in steps:
        assert step["id"] and step["label"]


# ── _is_dmaic_reachable ────────────────────────────────────────────────────────

def test_is_dmaic_reachable_success():
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    with patch("socket.create_connection", return_value=mock_conn):
        assert bridge._is_dmaic_reachable() is True


def test_is_dmaic_reachable_failure():
    with patch("socket.create_connection", side_effect=OSError("refused")):
        assert bridge._is_dmaic_reachable() is False


def test_is_dmaic_reachable_timeout():
    with patch("socket.create_connection", side_effect=TimeoutError()):
        assert bridge._is_dmaic_reachable() is False


# ── _is_dmaic_healthy ──────────────────────────────────────────────────────────

def _mock_urlopen(body: dict):
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(body).encode()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def test_is_dmaic_healthy_true():
    with patch("svas_interface.urlopen", return_value=_mock_urlopen({"status": "healthy"})):
        assert bridge._is_dmaic_healthy() is True


def test_is_dmaic_healthy_operational():
    with patch("svas_interface.urlopen", return_value=_mock_urlopen({"status": "operational"})):
        assert bridge._is_dmaic_healthy() is True


def test_is_dmaic_healthy_false_on_error():
    with patch("svas_interface.urlopen", side_effect=URLError("refused")):
        assert bridge._is_dmaic_healthy() is False


# ── _submit_phase ──────────────────────────────────────────────────────────────

def test_submit_phase_success():
    payload = {"status": "submitted", "phase_id": "dmaic-99"}
    with patch("svas_interface.urlopen", return_value=_mock_urlopen(payload)):
        result = bridge._submit_phase("improve model accuracy", "wf-9")
    assert result["status"] == "submitted"
    assert result["phase_id"] == "dmaic-99"


def test_submit_phase_returns_none_on_error():
    with patch("svas_interface.urlopen", side_effect=URLError("timeout")):
        assert bridge._submit_phase("intent", "wf-10") is None


def test_submit_phase_sends_correct_body():
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["data"] = json.loads(req.data.decode())
        captured["method"] = req.method
        return _mock_urlopen({"status": "submitted", "phase_id": "p"})

    with patch("svas_interface.urlopen", side_effect=fake_urlopen):
        bridge._submit_phase("analyze production drift patterns", "wf-abc")

    assert captured["data"]["intent"] == "analyze production drift patterns"
    assert "svas-wf-abc" in captured["data"]["workflow_id"]
    assert captured["method"] == "POST"


# ── analyze_intent (integration) ──────────────────────────────────────────────

def test_analyze_intent_mock_when_unreachable():
    with patch.object(bridge, "_is_dmaic_reachable", return_value=False):
        analysis, agent, steps = bridge.analyze_intent("wf-11", "improve model")
    assert "not reachable" in analysis
    assert agent == "GAI DMAIC Worker (AI/ML Quality)"


def test_analyze_intent_mock_when_unhealthy():
    with patch.object(bridge, "_is_dmaic_reachable", return_value=True), \
         patch.object(bridge, "_is_dmaic_healthy", return_value=False):
        analysis, _, _ = bridge.analyze_intent("wf-12", "improve model")
    assert "unhealthy" in analysis


def test_analyze_intent_mock_when_submit_fails():
    with patch.object(bridge, "_is_dmaic_reachable", return_value=True), \
         patch.object(bridge, "_is_dmaic_healthy", return_value=True), \
         patch.object(bridge, "_submit_phase", return_value=None):
        analysis, _, _ = bridge.analyze_intent("wf-13", "improve model")
    assert "submit-phase call failed" in analysis


def test_analyze_intent_live_path():
    fake = {"status": "submitted", "phase_id": "dmaic-live"}
    with patch.object(bridge, "_is_dmaic_reachable", return_value=True), \
         patch.object(bridge, "_is_dmaic_healthy", return_value=True), \
         patch.object(bridge, "_submit_phase", return_value=fake):
        analysis, agent, steps = bridge.analyze_intent("wf-14", "define model improvement scope")
    assert agent == "GAI DMAIC Worker (AI/ML Quality)"
    assert len(steps) == 5


def test_analyze_intent_context_ignored_safely():
    fake = {"status": "submitted", "phase_id": "dmaic-ctx"}
    with patch.object(bridge, "_is_dmaic_reachable", return_value=True), \
         patch.object(bridge, "_is_dmaic_healthy", return_value=True), \
         patch.object(bridge, "_submit_phase", return_value=fake):
        _, agent, _ = bridge.analyze_intent("wf-15", "intent", context={"k": "v"})
    assert agent == "GAI DMAIC Worker (AI/ML Quality)"


def test_analyze_intent_no_human_gate():
    fake = {"status": "submitted", "phase_id": "dmaic-gate"}
    with patch.object(bridge, "_is_dmaic_reachable", return_value=True), \
         patch.object(bridge, "_is_dmaic_healthy", return_value=True), \
         patch.object(bridge, "_submit_phase", return_value=fake):
        analysis, _, steps = bridge.analyze_intent("wf-16", "run quality control phase")
    assert "HUMAN REVIEW" not in analysis
    assert all(s["id"] != "s0" for s in steps)
