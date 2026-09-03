"""
D3 — Investigator Protocol and LocalLLMInvestigator

Responsibility: Accept the D2 bounded dict, call the local LLM, and return a
Pydantic-validated CausalHypothesis.  Nothing else.

Boundary (strict):
  INPUT   Bounded dict from InputFormatter (D2). No ReconciliationCase, no
          repository, no provider client, no V1 object crosses this boundary.
  OUTPUT  CausalHypothesis — a structured, Pydantic-validated untrusted claim.

D3 does NOT perform:
  - evidence-reference validation      → D4 (OutputValidator)
  - verification-intent allowlisting   → D4 (OutputValidator)
  - provider calls                     → D5 (DeterministicVerifier)
  - V1 reconciliation                  → D6 (InvestigationLoop)
  - case / incident mutation           → never
  - any write / mutation operation     → never

The Investigator protocol is model-agnostic.  D4–D6 import only this protocol
and the CausalHypothesis type; they are entirely unaware of Ollama, HTTP, or
any specific model.

Ollama integration:
  - Uses the Ollama JSON-schema structured-generation endpoint (/api/chat).
  - httpx is an existing dependency; no new packages are required.
  - The configured model MUST be available locally.  If the model is missing
    from the Ollama runtime, LocalLLMInvestigator raises OllamaModelNotFound
    immediately rather than silently falling back to a different model.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Protocol, runtime_checkable

import httpx
from pydantic import ValidationError

from src.domain.investigation.models import (
    CausalHypothesis,
    InvestigationDisposition,
    VerificationIntent,
)
from src.config.settings import LLMSettings

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Generation parameters — deterministic for reproducibility.
_TEMPERATURE: float = 0.0

# ---------------------------------------------------------------------------
# Investigator protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class Investigator(Protocol):
    """
    Model-agnostic interface for the LLM investigation layer.

    Implementations: LocalLLMInvestigator (D3).  GeminiInvestigator is
    deferred pending an empirical benchmark.

    Contract:
      - Input:  bounded dict produced by InputFormatter (D2)
      - Output: CausalHypothesis (untrusted structured claim)
      - May raise InvestigatorError on unrecoverable failure
      - Must NOT call providers, repositories, or V1
      - Must NOT mutate any shared state
    """

    def investigate(self, agent_input: Dict[str, Any]) -> CausalHypothesis:
        ...


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class InvestigatorError(Exception):
    """Base class for investigation-layer errors."""


class OllamaModelNotFound(InvestigatorError):
    """
    Raised when the pinned model is not available in the local Ollama runtime.
    The system MUST fail clearly rather than silently fall back to another model.
    """


class OllamaConnectionError(InvestigatorError):
    """Raised when the Ollama service cannot be reached."""


class StructuredOutputError(InvestigatorError):
    """Raised when the model response cannot be parsed into CausalHypothesis."""


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT: str = """You are an AI financial investigation assistant operating within a deterministic financial control system.

Your ONLY job is to analyze a single unresolved financial discrepancy and produce a structured causal hypothesis.

STRICT BOUNDARIES:
- You analyze ONLY the facts provided in the input (InvestigationContext). You do NOT invent evidence.
- You select verification intents ONLY from the permitted_verification_intents list. You do NOT suggest other queries.
- You reference ONLY evidence_ids that appear inside the evidence_records list. You do NOT use intent_id, payment_id, or fabricate evidence IDs.
- You do NOT determine financial truth. You propose a hypothesis for deterministic verification.
- Your confidence value (LOW/MEDIUM/HIGH) is informational only.
- If no permitted verification can resolve the stalemate, set disposition to INVESTIGATION_EXHAUSTED and leave verification_intents empty.
- Every substantive claim must reference evidence from InvestigationContext, or explicitly identify the required information as missing.

You MUST respond with a JSON object conforming EXACTLY to this schema:
{
  "hypothesis_id": "<unique_identifier_for_this_claim>",
  "claim": "<concise falsifiable explanation of why the discrepancy occurred>",
  "supporting_evidence_ids": ["<evidence_id from input>", ...],
  "contradicting_evidence_ids": ["<evidence_id from input>", ...],
  "missing_evidence": "<what evidence would discriminate between hypotheses>",
  "confidence": "LOW" | "MEDIUM" | "HIGH",
  "disposition": "VERIFICATION_PROPOSED" | "INVESTIGATION_EXHAUSTED",
  "verification_intents": ["QUERY_PROVIDER_STATE", ...]
}

Rules:
- verification_intents MUST be non-empty when disposition is VERIFICATION_PROPOSED.
- verification_intents MUST be empty when disposition is INVESTIGATION_EXHAUSTED.
- verification_intents MUST contain ONLY values in permitted_verification_intents from the input.
- Do NOT include any text outside the JSON object.
"""


def _build_user_message(agent_input: Dict[str, Any]) -> str:
    """Serialize the bounded case dict into the user message."""
    return (
        "Analyze the following unresolved financial discrepancy and return your "
        "structured hypothesis:\n\n"
        + json.dumps(agent_input, indent=2, default=str)
    )


# ---------------------------------------------------------------------------
# Ollama JSON-schema enforcement
# ---------------------------------------------------------------------------

# Ollama structured generation schema derived directly from CausalHypothesis.
# Kept here rather than generated dynamically so the exact schema is pinned
# and visible to reviewers.
_CAUSAL_HYPOTHESIS_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": [
        "hypothesis_id",
        "claim",
        "supporting_evidence_ids",
        "contradicting_evidence_ids",
        "missing_evidence",
        "confidence",
        "disposition",
        "verification_intents"
    ],
    "properties": {
        "hypothesis_id":                {"type": "string"},
        "claim":                        {"type": "string"},
        "supporting_evidence_ids":      {"type": "array", "items": {"type": "string"}},
        "contradicting_evidence_ids":   {"type": "array", "items": {"type": "string"}},
        "missing_evidence":             {"type": "string"},
        "confidence":                   {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]},
        "disposition":                  {
            "type": "string",
            "enum": ["VERIFICATION_PROPOSED", "INVESTIGATION_EXHAUSTED"],
        },
        "verification_intents": {
            "type": "array",
            "items": {"type": "string", "enum": [v.value for v in VerificationIntent]}
        },
    },
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# LocalLLMInvestigator
# ---------------------------------------------------------------------------

class LocalLLMInvestigator:
    """
    Investigator implementation backed by a local Ollama model.

    This class is the ONLY component in the investigation stack that knows
    about Ollama.  Everything downstream (D4 Validator, D5 Verifier, D6 Loop)
    depends only on the Investigator protocol and CausalHypothesis.

    Model availability check:
      __init__ immediately verifies that the configured model is present in the Ollama
      runtime.  If not, OllamaModelNotFound is raised.  This prevents silent
      fallback to a different model.
    """

    def __init__(
        self,
        settings: LLMSettings,
    ) -> None:
        """
        Initializes the investigator with injected LLMSettings.
        """
        self._model = settings.model_name
        self._timeout = settings.timeout_seconds
        self._temperature = _TEMPERATURE
        
        self._chat_url = f"{settings.base_url}/api/chat"
        self._tags_url = f"{settings.base_url}/api/tags"
        self._verify_model_available()

    def _verify_model_available(self) -> None:
        """
        Query the Ollama runtime to confirm the pinned model is present.
        Raises OllamaModelNotFound if not.  Raises OllamaConnectionError
        if the service is unreachable.
        """
        try:
            response = httpx.get(self._tags_url, timeout=3.0)
            response.raise_for_status()
        except (httpx.TimeoutException, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
            raise OllamaConnectionError(
                f"Timeout connecting to Ollama at {self._tags_url}. "
                "Is Ollama running?"
            ) from exc
        except httpx.ConnectError as exc:
            raise OllamaConnectionError(
                f"Cannot connect to Ollama at {self._tags_url}. "
                "Is Ollama running?"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise OllamaConnectionError(
                f"Ollama returned an error: {exc.response.status_code}"
            ) from exc

        tags_data = response.json()
        available = {m["name"] for m in tags_data.get("models", [])}
        if self._model not in available:
            raise OllamaModelNotFound(
                f"Pinned model '{self._model}' is not available in the local Ollama "
                f"runtime. Available models: {sorted(available)}. "
                f"Pull it with: ollama pull {self._model}"
            )

    def investigate(self, agent_input: Dict[str, Any]) -> CausalHypothesis:
        """
        Send the bounded agent_input dict to the local LLM and return a
        validated CausalHypothesis.

        The agent_input must be the exact dict produced by InputFormatter (D2).
        No other objects are accepted.

        Raises:
            OllamaConnectionError    if the HTTP call fails
            StructuredOutputError    if the response cannot be parsed
        """
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": _build_user_message(agent_input)},
            ],
            "stream": False,
            "options": {"temperature": self._temperature},
            "format": _CAUSAL_HYPOTHESIS_SCHEMA,
        }

        try:
            response = httpx.post(
                self._chat_url,
                json=payload,
                timeout=self._timeout,
            )
            response.raise_for_status()
        except httpx.ConnectError as exc:
            from src.observability.metrics import inc_a3_failure
            inc_a3_failure("connection")
            raise OllamaConnectionError(
                f"Cannot connect to Ollama at {self._chat_url}"
            ) from exc
        except httpx.TimeoutException as exc:
            from src.observability.metrics import inc_a3_failure
            inc_a3_failure("timeout")
            raise OllamaConnectionError(
                f"Ollama timed out after {self._timeout}s"
            ) from exc
        except httpx.HTTPStatusError as exc:
            from src.observability.metrics import inc_a3_failure
            inc_a3_failure("http_status")
            raise OllamaConnectionError(
                f"Ollama returned HTTP {exc.response.status_code}"
            ) from exc

        raw_content = self._extract_content(response.json())
        try:
            return self._parse_hypothesis(raw_content)
        except StructuredOutputError:
            from src.observability.metrics import inc_a3_failure
            inc_a3_failure("structured_output")
            raise

    @staticmethod
    def _extract_content(response_json: Dict[str, Any]) -> str:
        """Extract the text content from the Ollama /api/chat response."""
        try:
            return response_json["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise StructuredOutputError(
                f"Unexpected Ollama response structure: {response_json!r}"
            ) from exc

    @staticmethod
    def _parse_hypothesis(raw_content: str) -> CausalHypothesis:
        """
        Parse the raw model string into a CausalHypothesis.

        Two-stage:
          1. JSON decode  — catches malformed JSON
          2. Pydantic parse — enforces schema + cross-field validators
        """
        try:
            data = json.loads(raw_content)
        except json.JSONDecodeError as exc:
            raise StructuredOutputError(
                f"Model response is not valid JSON: {raw_content!r}"
            ) from exc

        try:
            return CausalHypothesis.model_validate(data)
        except ValidationError as exc:
            raise StructuredOutputError(
                f"Model response does not conform to CausalHypothesis schema: {exc}"
            ) from exc
