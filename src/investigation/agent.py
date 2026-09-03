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

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# The single, pinned model artifact.  Change this constant when the model
# selection changes; do not allow callers to supply an arbitrary model name.
PINNED_MODEL: str = "qwen3:8b"

OLLAMA_BASE_URL: str = "http://localhost:11434"
_CHAT_ENDPOINT: str = f"{OLLAMA_BASE_URL}/api/chat"
_TAGS_ENDPOINT: str = f"{OLLAMA_BASE_URL}/api/tags"

# Generation parameters — deterministic for reproducibility.
_TEMPERATURE: float = 0.0
_TIMEOUT_SECONDS: float = 120.0  # local inference can be slow

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

Your ONLY job is to analyze a single unresolved financial discrepancy and produce a structured hypothesis.

STRICT BOUNDARIES:
- You analyze ONLY the facts provided in the input. You do NOT invent evidence.
- You select a verification intent ONLY from the permitted_verification_intents list. You do NOT suggest other queries.
- You reference ONLY evidence_ids that appear in the input. You do NOT fabricate evidence IDs.
- You do NOT determine financial truth. You propose a hypothesis for deterministic verification.
- Your confidence value (LOW/MEDIUM/HIGH) is informational only. It has zero effect on what happens next.
- If no permitted verification can resolve the stalemate, set disposition to INVESTIGATION_EXHAUSTED and omit verification_intent.

You MUST respond with a JSON object conforming EXACTLY to this schema:
{
  "hypothesis": "<concise falsifiable explanation of why the discrepancy occurred>",
  "supporting_evidence_ids": ["<evidence_id from input>", ...],
  "contradicting_evidence_ids": ["<evidence_id from input>", ...],
  "missing_evidence_description": "<what evidence would discriminate between hypotheses>",
  "confidence": "LOW" | "MEDIUM" | "HIGH",
  "disposition": "VERIFICATION_PROPOSED" | "INVESTIGATION_EXHAUSTED",
  "verification_intent": "QUERY_PROVIDER_REFUND" | "QUERY_PROVIDER_PAYMENT" | "QUERY_REFUND_EVENTS" | null
}

Rules:
- verification_intent MUST be non-null when disposition is VERIFICATION_PROPOSED.
- verification_intent MUST be null when disposition is INVESTIGATION_EXHAUSTED.
- verification_intent MUST be one of the values in permitted_verification_intents from the input.
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
        "hypothesis",
        "supporting_evidence_ids",
        "contradicting_evidence_ids",
        "missing_evidence_description",
        "confidence",
        "disposition",
    ],
    "properties": {
        "hypothesis":                   {"type": "string"},
        "supporting_evidence_ids":      {"type": "array", "items": {"type": "string"}},
        "contradicting_evidence_ids":   {"type": "array", "items": {"type": "string"}},
        "missing_evidence_description": {"type": "string"},
        "confidence":                   {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]},
        "disposition":                  {
            "type": "string",
            "enum": ["VERIFICATION_PROPOSED", "INVESTIGATION_EXHAUSTED"],
        },
        "verification_intent": {
            "oneOf": [
                {"type": "string", "enum": [v.value for v in VerificationIntent]},
                {"type": "null"},
            ]
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
      __init__ immediately verifies that PINNED_MODEL is present in the Ollama
      runtime.  If not, OllamaModelNotFound is raised.  This prevents silent
      fallback to a different model.
    """

    def __init__(
        self,
        model: str = PINNED_MODEL,
        base_url: str = OLLAMA_BASE_URL,
        temperature: float = _TEMPERATURE,
        timeout: float = _TIMEOUT_SECONDS,
    ) -> None:
        self._model = model
        self._chat_url = f"{base_url}/api/chat"
        self._tags_url = f"{base_url}/api/tags"
        self._temperature = temperature
        self._timeout = timeout
        self._verify_model_available()

    def _verify_model_available(self) -> None:
        """
        Query the Ollama runtime to confirm the pinned model is present.
        Raises OllamaModelNotFound if not.  Raises OllamaConnectionError
        if the service is unreachable.
        """
        try:
            response = httpx.get(self._tags_url, timeout=10.0)
            response.raise_for_status()
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
            raise OllamaConnectionError(
                f"Cannot connect to Ollama at {self._chat_url}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise OllamaConnectionError(
                f"Ollama returned HTTP {exc.response.status_code}"
            ) from exc

        raw_content = self._extract_content(response.json())
        return self._parse_hypothesis(raw_content)

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
