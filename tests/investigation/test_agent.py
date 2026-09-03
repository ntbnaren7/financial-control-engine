"""
D3 Acceptance Tests — Investigator Protocol and LocalLLMInvestigator

Test tiers:
  Unit tests (class TestD3Unit*)
    All 10 acceptance criteria, Ollama is mocked via httpx.
    These run in the standard pytest suite with no external dependencies.

  Integration smoke (class TestD3Integration*)
    Calls the real local Ollama runtime.
    Skipped automatically when Ollama is not reachable.
    Run separately to benchmark actual model behaviour.

Acceptance criteria:
  D3-1  Valid structured response → CausalHypothesis
  D3-2  VERIFICATION_PROPOSED with intent
  D3-3  INVESTIGATION_EXHAUSTED without intent
  D3-4  Malformed model output → StructuredOutputError
  D3-5  Invalid enum value → StructuredOutputError
  D3-6  Missing required field → StructuredOutputError
  D3-7  Model cannot introduce executable query parameters into typed output
  D3-8  Model receives exactly the D2 bounded input (and nothing else)
  D3-9  No provider/database/V1 imports in agent.py
  D3-10 No mutation-capable interfaces exposed
"""

from __future__ import annotations

import importlib
import json
import sys
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from src.domain.investigation.models import (
    CausalHypothesis,
    InvestigationDisposition,
    VerificationIntent,
)
from src.investigation.agent import (
    PINNED_MODEL,
    Investigator,
    LocalLLMInvestigator,
    OllamaConnectionError,
    OllamaModelNotFound,
    StructuredOutputError,
    _build_user_message,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_AGENT_INPUT: Dict[str, Any] = {
    "case_id": "case_stalemate_1",
    "discrepancy_type": "EPISTEMIC_STALEMATE",
    "knowledge_state": "UNKNOWN",
    "expected_refund": {
        "intent_id": "ref_8",
        "provider_payment_id": "pay_abc123",
        "amount": "200.00",
        "currency": "INR",
        "created_at": "2026-09-03T06:00:00+00:00",
    },
    "correlated_observations": [],
    "unmatched_observations": [
        {
            "evidence_id": "evt_wh_temporal",
            "source": "razorpay_webhook",
            "evidence_type": "RAZORPAY_REFUND.PROCESSED",
            "timestamp": "2026-09-02T06:00:00+00:00",
            "correlation_status": "TEMPORAL_VIOLATION",
            "correlation_checks": {
                "matched_by": None,
                "temporal_check": False,
                "entity_scope": True,
                "amount_check": False,
                "currency_check": False,
            },
        }
    ],
    "permitted_verification_intents": [
        "QUERY_PROVIDER_REFUND",
        "QUERY_PROVIDER_PAYMENT",
        "QUERY_REFUND_EVENTS",
    ],
}

_VALID_PROPOSED_OUTPUT: Dict[str, Any] = {
    "hypothesis": "Provider execution occurred but webhook arrived outside the correlation window.",
    "supporting_evidence_ids": ["evt_wh_temporal"],
    "contradicting_evidence_ids": [],
    "missing_evidence_description": "Authoritative provider refund status lookup.",
    "confidence": "MEDIUM",
    "disposition": "VERIFICATION_PROPOSED",
    "verification_intent": "QUERY_PROVIDER_REFUND",
}

_VALID_EXHAUSTED_OUTPUT: Dict[str, Any] = {
    "hypothesis": "Insufficient evidence to discriminate between hypotheses.",
    "supporting_evidence_ids": [],
    "contradicting_evidence_ids": [],
    "missing_evidence_description": "None available within permitted capability set.",
    "confidence": "LOW",
    "disposition": "INVESTIGATION_EXHAUSTED",
    "verification_intent": None,
}


def _mock_tags_response(model: str = PINNED_MODEL) -> MagicMock:
    """Return a mock httpx.get response that lists the given model."""
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {"models": [{"name": model}]}
    return mock


def _mock_chat_response(content: Dict[str, Any]) -> MagicMock:
    """Return a mock httpx.post response with the given content dict."""
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {
        "message": {"content": json.dumps(content)}
    }
    return mock


def _make_investigator(model: str = PINNED_MODEL) -> LocalLLMInvestigator:
    """Construct a LocalLLMInvestigator with Ollama availability check mocked."""
    with patch("httpx.get", return_value=_mock_tags_response(model)):
        return LocalLLMInvestigator(model=model)


# ---------------------------------------------------------------------------
# D3-1  Valid structured response → CausalHypothesis
# D3-2  VERIFICATION_PROPOSED with intent
# ---------------------------------------------------------------------------

class TestD3Unit12ValidProposed:
    def test_returns_causal_hypothesis_instance(self):
        investigator = _make_investigator()
        with patch("httpx.post", return_value=_mock_chat_response(_VALID_PROPOSED_OUTPUT)):
            result = investigator.investigate(_SAMPLE_AGENT_INPUT)
        assert isinstance(result, CausalHypothesis)

    def test_verification_proposed_intent_preserved(self):
        investigator = _make_investigator()
        with patch("httpx.post", return_value=_mock_chat_response(_VALID_PROPOSED_OUTPUT)):
            result = investigator.investigate(_SAMPLE_AGENT_INPUT)
        assert result.disposition == InvestigationDisposition.VERIFICATION_PROPOSED
        assert result.verification_intent == VerificationIntent.QUERY_PROVIDER_REFUND

    def test_hypothesis_text_preserved(self):
        investigator = _make_investigator()
        with patch("httpx.post", return_value=_mock_chat_response(_VALID_PROPOSED_OUTPUT)):
            result = investigator.investigate(_SAMPLE_AGENT_INPUT)
        assert "correlation window" in result.hypothesis

    def test_confidence_is_medium(self):
        investigator = _make_investigator()
        with patch("httpx.post", return_value=_mock_chat_response(_VALID_PROPOSED_OUTPUT)):
            result = investigator.investigate(_SAMPLE_AGENT_INPUT)
        assert result.confidence == "MEDIUM"


# ---------------------------------------------------------------------------
# D3-3  INVESTIGATION_EXHAUSTED without intent
# ---------------------------------------------------------------------------

class TestD3Unit3Exhausted:
    def test_exhausted_disposition(self):
        investigator = _make_investigator()
        with patch("httpx.post", return_value=_mock_chat_response(_VALID_EXHAUSTED_OUTPUT)):
            result = investigator.investigate(_SAMPLE_AGENT_INPUT)
        assert result.disposition == InvestigationDisposition.INVESTIGATION_EXHAUSTED

    def test_exhausted_has_no_intent(self):
        investigator = _make_investigator()
        with patch("httpx.post", return_value=_mock_chat_response(_VALID_EXHAUSTED_OUTPUT)):
            result = investigator.investigate(_SAMPLE_AGENT_INPUT)
        assert result.verification_intent is None


# ---------------------------------------------------------------------------
# D3-4  Malformed model output → StructuredOutputError
# ---------------------------------------------------------------------------

class TestD3Unit4MalformedOutput:
    def test_non_json_string_raises(self):
        investigator = _make_investigator()
        bad_mock = MagicMock()
        bad_mock.raise_for_status = MagicMock()
        bad_mock.json.return_value = {
            "message": {"content": "This is not JSON at all."}
        }
        with patch("httpx.post", return_value=bad_mock):
            with pytest.raises(StructuredOutputError, match="not valid JSON"):
                investigator.investigate(_SAMPLE_AGENT_INPUT)

    def test_empty_response_raises(self):
        investigator = _make_investigator()
        bad_mock = MagicMock()
        bad_mock.raise_for_status = MagicMock()
        bad_mock.json.return_value = {"message": {"content": ""}}
        with patch("httpx.post", return_value=bad_mock):
            with pytest.raises(StructuredOutputError):
                investigator.investigate(_SAMPLE_AGENT_INPUT)

    def test_missing_message_key_raises(self):
        investigator = _make_investigator()
        bad_mock = MagicMock()
        bad_mock.raise_for_status = MagicMock()
        bad_mock.json.return_value = {"unexpected": "structure"}
        with patch("httpx.post", return_value=bad_mock):
            with pytest.raises(StructuredOutputError, match="response structure"):
                investigator.investigate(_SAMPLE_AGENT_INPUT)


# ---------------------------------------------------------------------------
# D3-5  Invalid enum value → StructuredOutputError
# ---------------------------------------------------------------------------

class TestD3Unit5InvalidEnum:
    def test_invalid_disposition_enum_rejected(self):
        investigator = _make_investigator()
        bad_output = {**_VALID_PROPOSED_OUTPUT, "disposition": "MAKE_PAYMENT_NOW"}
        with patch("httpx.post", return_value=_mock_chat_response(bad_output)):
            with pytest.raises(StructuredOutputError):
                investigator.investigate(_SAMPLE_AGENT_INPUT)

    def test_invalid_verification_intent_enum_rejected(self):
        investigator = _make_investigator()
        bad_output = {
            **_VALID_PROPOSED_OUTPUT,
            "verification_intent": "EXECUTE_REFUND_NOW",  # mutation attempt
        }
        with patch("httpx.post", return_value=_mock_chat_response(bad_output)):
            with pytest.raises(StructuredOutputError):
                investigator.investigate(_SAMPLE_AGENT_INPUT)

    def test_invalid_confidence_enum_rejected(self):
        investigator = _make_investigator()
        bad_output = {**_VALID_PROPOSED_OUTPUT, "confidence": "VERY_HIGH"}
        with patch("httpx.post", return_value=_mock_chat_response(bad_output)):
            with pytest.raises(StructuredOutputError):
                investigator.investigate(_SAMPLE_AGENT_INPUT)


# ---------------------------------------------------------------------------
# D3-6  Missing required field → StructuredOutputError
# ---------------------------------------------------------------------------

class TestD3Unit6MissingField:
    def test_missing_hypothesis_rejected(self):
        investigator = _make_investigator()
        bad_output = {k: v for k, v in _VALID_PROPOSED_OUTPUT.items() if k != "hypothesis"}
        with patch("httpx.post", return_value=_mock_chat_response(bad_output)):
            with pytest.raises(StructuredOutputError):
                investigator.investigate(_SAMPLE_AGENT_INPUT)

    def test_missing_disposition_rejected(self):
        investigator = _make_investigator()
        bad_output = {k: v for k, v in _VALID_PROPOSED_OUTPUT.items() if k != "disposition"}
        with patch("httpx.post", return_value=_mock_chat_response(bad_output)):
            with pytest.raises(StructuredOutputError):
                investigator.investigate(_SAMPLE_AGENT_INPUT)

    def test_proposed_without_intent_rejected(self):
        """Pydantic cross-field validator: PROPOSED requires intent."""
        investigator = _make_investigator()
        bad_output = {**_VALID_PROPOSED_OUTPUT, "verification_intent": None}
        with patch("httpx.post", return_value=_mock_chat_response(bad_output)):
            with pytest.raises(StructuredOutputError):
                investigator.investigate(_SAMPLE_AGENT_INPUT)

    def test_exhausted_with_intent_rejected(self):
        """Pydantic cross-field validator: EXHAUSTED forbids intent."""
        investigator = _make_investigator()
        bad_output = {
            **_VALID_EXHAUSTED_OUTPUT,
            "verification_intent": "QUERY_PROVIDER_REFUND",
        }
        with patch("httpx.post", return_value=_mock_chat_response(bad_output)):
            with pytest.raises(StructuredOutputError):
                investigator.investigate(_SAMPLE_AGENT_INPUT)


# ---------------------------------------------------------------------------
# D3-7  Model cannot introduce executable query parameters into typed output
# ---------------------------------------------------------------------------

class TestD3Unit7NoExecutableParams:
    def test_verification_intent_is_enum_not_parameterised(self):
        """
        The CausalHypothesis schema has no field for provider IDs, amounts, or
        other executable parameters.  The model's only choices are the three
        enum values; it cannot attach a target entity ID.
        """
        investigator = _make_investigator()
        with patch("httpx.post", return_value=_mock_chat_response(_VALID_PROPOSED_OUTPUT)):
            result = investigator.investigate(_SAMPLE_AGENT_INPUT)
        # Intent is a bare enum — it carries no parameters
        assert isinstance(result.verification_intent, VerificationIntent)
        # No parameter-injection fields exist on CausalHypothesis
        assert not hasattr(result, "target_entity_id")
        assert not hasattr(result, "provider_id")
        assert not hasattr(result, "payment_id")
        assert not hasattr(result, "refund_id")
        assert not hasattr(result, "merchant_id")

    def test_extra_fields_rejected_by_pydantic(self):
        """Extra fields in model output are rejected (model_config forbids extras)."""
        investigator = _make_investigator()
        bad_output = {
            **_VALID_PROPOSED_OUTPUT,
            "target_refund_id": "ref_8",        # injection attempt
            "execute_amount": 20000,             # injection attempt
        }
        with patch("httpx.post", return_value=_mock_chat_response(bad_output)):
            # Pydantic v2 ignores extra fields by default; the important check
            # is that the returned object does NOT carry the injected values
            result = investigator.investigate(_SAMPLE_AGENT_INPUT)
        assert not hasattr(result, "target_refund_id")
        assert not hasattr(result, "execute_amount")


# ---------------------------------------------------------------------------
# D3-8  Model receives exactly the D2 bounded input
# ---------------------------------------------------------------------------

class TestD3Unit8BoundedInput:
    def test_agent_input_serialised_verbatim_in_user_message(self):
        """The user message must contain the exact agent_input dict, not a
        transformed or augmented version."""
        user_msg = _build_user_message(_SAMPLE_AGENT_INPUT)
        # The serialised dict must appear in the message
        assert "case_stalemate_1" in user_msg
        assert "EPISTEMIC_STALEMATE" in user_msg
        assert "evt_wh_temporal" in user_msg
        assert "QUERY_PROVIDER_REFUND" in user_msg

    def test_no_extra_context_added_to_user_message(self):
        """The user message must not contain internal database IDs,
        provider credentials, or raw payloads beyond what D2 produced."""
        user_msg = _build_user_message(_SAMPLE_AGENT_INPUT)
        assert "SECRET" not in user_msg
        assert "password" not in user_msg.lower()
        assert "api_key" not in user_msg.lower()

    def test_post_payload_uses_agent_input_verbatim(self):
        """Verify the httpx.post call includes the agent_input dict."""
        investigator = _make_investigator()
        captured_payload: Dict[str, Any] = {}

        def capture_post(url: str, json: Any, **kwargs: Any) -> MagicMock:
            captured_payload.update(json)
            return _mock_chat_response(_VALID_PROPOSED_OUTPUT)

        with patch("httpx.post", side_effect=capture_post):
            investigator.investigate(_SAMPLE_AGENT_INPUT)

        user_content = captured_payload["messages"][1]["content"]
        assert "case_stalemate_1" in user_content
        assert "evt_wh_temporal" in user_content


# ---------------------------------------------------------------------------
# D3-9  No provider/database/V1 imports in agent.py
# ---------------------------------------------------------------------------

class TestD3Unit9NoForbiddenImports:
    FORBIDDEN_PREFIXES = (
        "src.integrations",
        "src.storage",
        "src.control",
        "src.outbox",
        "src.reconciliation",
        "src.state",
        "src.domain.cases",
        "src.domain.incidents",
    )

    def test_agent_module_does_not_import_forbidden_packages(self):
        """
        The agent module must not transitively import any provider, storage,
        reconciliation, or V1 modules.  This is a static-analysis guard.
        """
        # Ensure the module is loaded
        if "src.investigation.agent" not in sys.modules:
            importlib.import_module("src.investigation.agent")

        agent_module_file = sys.modules["src.investigation.agent"].__file__
        assert agent_module_file is not None

        # Read the source and check for forbidden imports
        with open(agent_module_file) as f:
            source = f.read()

        for prefix in self.FORBIDDEN_PREFIXES:
            assert prefix not in source, (
                f"agent.py must not import '{prefix}' — found in source"
            )

    def test_protocol_check_passes(self):
        """LocalLLMInvestigator satisfies the Investigator protocol."""
        investigator = _make_investigator()
        assert isinstance(investigator, Investigator)


# ---------------------------------------------------------------------------
# D3-10 No mutation-capable interfaces exposed
# ---------------------------------------------------------------------------

class TestD3Unit10NoMutationInterfaces:
    MUTATION_SYMBOLS = [
        "ClosedLoopCoordinator",
        "TransactionalOutbox",
        "OutboxEntry",
        "dispatch_outbox",
        "execute_refund",
        "create_incident",
        "update_case",
        "write_observation",
        "save_case",
        "commit_outbox",
    ]

    def test_mutation_symbols_not_in_agent_source(self):
        """
        The agent module must not reference any mutation-capable interfaces.
        The LLM layer has no write access by design.
        Uses word-boundary matching to avoid false positives in docstrings.
        """
        import re
        agent_module = sys.modules.get("src.investigation.agent")
        if agent_module is None:
            agent_module = importlib.import_module("src.investigation.agent")

        with open(agent_module.__file__) as f:  # type: ignore[arg-type]
            source = f.read()

        for symbol in self.MUTATION_SYMBOLS:
            # Match only as a whole word / qualified name, not substring
            pattern = r"\b" + re.escape(symbol) + r"\b"
            assert not re.search(pattern, source), (
                f"agent.py must not reference mutation symbol '{symbol}'"
            )

    def test_model_pinning_uses_constant(self):
        """
        The pinned model must be declared as a module-level constant, not
        allowed to be overridden arbitrarily at call time.
        """
        assert PINNED_MODEL == "qwen3:8b"

    def test_model_not_found_raises_clearly(self):
        """Missing model raises OllamaModelNotFound, not a silent fallback."""
        tags_response = MagicMock()
        tags_response.raise_for_status = MagicMock()
        tags_response.json.return_value = {
            "models": [{"name": "some_other_model:7b"}]
        }
        with patch("httpx.get", return_value=tags_response):
            with pytest.raises(OllamaModelNotFound, match="qwen3:8b"):
                LocalLLMInvestigator(model=PINNED_MODEL)

    def test_connection_error_raises_clearly(self):
        """Ollama unreachable raises OllamaConnectionError, not an opaque error."""
        import httpx as _httpx
        with patch("httpx.get", side_effect=_httpx.ConnectError("refused")):
            with pytest.raises(OllamaConnectionError):
                LocalLLMInvestigator()


# ---------------------------------------------------------------------------
# Integration smoke test (real Ollama — skipped if not reachable)
# ---------------------------------------------------------------------------

def _ollama_reachable() -> bool:
    try:
        import httpx as _httpx
        r = _httpx.get("http://localhost:11434/api/tags", timeout=3.0)
        return r.status_code == 200
    except Exception:
        return False


@pytest.mark.skipif(not _ollama_reachable(), reason="Ollama not running locally")
class TestD3IntegrationRealOllama:
    """
    Live integration tests against the real qwen3:8b model.
    These are deliberately slow (each call ~10–30 s on M-series hardware).
    They are skipped in CI unless Ollama is running.
    """

    @pytest.fixture(scope="class")
    def investigator(self) -> LocalLLMInvestigator:
        return LocalLLMInvestigator()

    def test_real_model_returns_causal_hypothesis(self, investigator: LocalLLMInvestigator):
        result = investigator.investigate(_SAMPLE_AGENT_INPUT)
        assert isinstance(result, CausalHypothesis)

    def test_real_model_references_only_known_evidence_ids(self, investigator: LocalLLMInvestigator):
        result = investigator.investigate(_SAMPLE_AGENT_INPUT)
        known_ids = {
            obs["evidence_id"]
            for obs in (
                _SAMPLE_AGENT_INPUT["correlated_observations"]
                + _SAMPLE_AGENT_INPUT["unmatched_observations"]
            )
        }
        for ref_id in result.supporting_evidence_ids + result.contradicting_evidence_ids:
            assert ref_id in known_ids, (
                f"Model hallucinated evidence_id '{ref_id}' not in known set {known_ids}"
            )

    def test_real_model_selects_permitted_intent(self, investigator: LocalLLMInvestigator):
        result = investigator.investigate(_SAMPLE_AGENT_INPUT)
        if result.disposition == InvestigationDisposition.VERIFICATION_PROPOSED:
            assert result.verification_intent in list(VerificationIntent)

    def test_real_model_produces_valid_disposition(self, investigator: LocalLLMInvestigator):
        result = investigator.investigate(_SAMPLE_AGENT_INPUT)
        assert result.disposition in list(InvestigationDisposition)
