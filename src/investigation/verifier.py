"""
D5 — Deterministic Verifier (V2)

Responsibility: Execute read-only provider queries based on the LLM's validated
verification intents and return a structured VerificationResult containing the 
new Evidence and Normalized Observations.

Strict invariants:
  1. Input: CausalHypothesis + trusted InvestigationContext.
  2. Query parameters are derived 100% from the InvestigationContext.
  3. The LLM's text/IDs CANNOT influence the query parameters.
  4. Only read-only provider calls are executed.
  5. Provider routing is explicit via correlation_keys.provider.
  6. No financial classification or mutation occurs here.
"""

from typing import List, Dict
import uuid
from datetime import datetime, timezone

from src.domain.investigation.context import InvestigationContext
from src.domain.investigation.models import (
    CausalHypothesis,
    InvestigationDisposition,
    VerificationResult,
    VerificationStatus,
    VerificationRejectionReason
)
from src.integrations.verifier import ProviderVerifier, RazorpayVerifier
from src.integrations.razorpay.provider import RazorpayProvider

class DeterministicVerifier:
    """
    Translates a validated verification intent into a deterministic,
    read-only provider query, using parameters sourced strictly from the
    trusted InvestigationContext.
    """

    def __init__(self, razorpay_provider: RazorpayProvider) -> None:
        # Simple registry of authorized providers
        self._providers: Dict[str, ProviderVerifier] = {
            "razorpay": RazorpayVerifier(razorpay_provider)
        }

    async def verify(
        self,
        hypothesis: CausalHypothesis,
        context: InvestigationContext,
    ) -> List[VerificationResult]:
        """
        Execute the verification intents proposed by the hypothesis.

        Parameters
        ----------
        hypothesis : CausalHypothesis
            The validated hypothesis from D4 (OutputValidator).
        context : InvestigationContext
            The trusted immutable facts. Query parameters are derived from here.

        Returns
        -------
        List[VerificationResult]
            A list of structured verification results, one for each intent, 
            containing new Evidence and Normalized Observations if successful.
        """
        if hypothesis.disposition == InvestigationDisposition.INVESTIGATION_EXHAUSTED:
            return []

        results: List[VerificationResult] = []

        for intent in hypothesis.verification_intents:
            # 1. Trusted Provider Routing
            provider = None
            if context.expectation and context.expectation.correlation_keys.provider:
                provider = context.expectation.correlation_keys.provider
            
            # Fallback to observations if expectation lacks explicit provider mapping
            if not provider and context.observations:
                provider = context.observations[0].provider

            if not provider:
                results.append(
                    VerificationResult(
                        verification_id=str(uuid.uuid4()),
                        intent=intent,
                        status=VerificationStatus.REJECTED,
                        evidence_ids=[],
                        new_observations=[],
                        failure_reason=VerificationRejectionReason.MISSING_PARAMETERS.value,
                        verified_at=datetime.now(timezone.utc)
                    )
                )
                from src.observability.metrics import inc_a4_verification
                inc_a4_verification("unknown", VerificationStatus.REJECTED.value)
                continue

            verifier = self._providers.get(provider.lower())
            if not verifier:
                results.append(
                    VerificationResult(
                        verification_id=str(uuid.uuid4()),
                        intent=intent,
                        status=VerificationStatus.REJECTED,
                        evidence_ids=[],
                        new_observations=[],
                        failure_reason=f"Unsupported provider: {provider}",
                        verified_at=datetime.now(timezone.utc)
                    )
                )
                from src.observability.metrics import inc_a4_verification
                inc_a4_verification(provider.lower(), VerificationStatus.REJECTED.value)
                continue

            # 2. Execute via Provider Strategy
            import time
            start_time = time.monotonic()
            try:
                result = await verifier.verify(intent, context)
            finally:
                elapsed = time.monotonic() - start_time
                from src.observability.metrics import observe_provider_latency
                observe_provider_latency(provider.lower(), elapsed)

            from src.observability.metrics import inc_a4_verification
            inc_a4_verification(provider.lower(), result.status.value)
            results.append(result)

        return results
