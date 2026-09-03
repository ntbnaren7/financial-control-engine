"""
D5 — Deterministic Verifier

Responsibility: Execute read-only provider queries based on the LLM's validated
verification intent.

Strict invariants:
  1. Input: CausalHypothesis + trusted ReconciliationCase.
  2. Query parameters are derived 100% from the ReconciliationCase.
  3. The LLM's text/IDs CANNOT influence the query parameters.
  4. Only read-only provider calls are executed.
  5. Provider responses pass through Phase C normalization.
  6. No financial classification or mutation occurs here.
"""

from typing import List, Union

import httpx

from src.domain.cases.models import ReconciliationCase
from src.domain.evidence.normalization import RazorpayApiNormalizer
from src.domain.investigation.models import (
    CausalHypothesis,
    InvestigationDisposition,
    VerificationIntent,
    VerificationRejection,
    VerificationRejectionReason,
)
from src.domain.evidence.models import Evidence
from src.integrations.razorpay.client import RazorpayClient

VerificationResult = Union[List[Evidence], VerificationRejection]


class DeterministicVerifier:
    """
    Translates a validated verification intent into a deterministic,
    read-only provider query, using parameters sourced strictly from the
    trusted case expectation.
    """

    def __init__(self, razorpay_client: RazorpayClient) -> None:
        self._client = razorpay_client
        self._normalizer = RazorpayApiNormalizer()

    async def verify(
        self,
        hypothesis: CausalHypothesis,
        case: ReconciliationCase,
    ) -> VerificationResult:
        """
        Execute the verification intent proposed by the hypothesis.

        Parameters
        ----------
        hypothesis : CausalHypothesis
            The validated hypothesis from D4 (OutputValidator).
        case : ReconciliationCase
            The trusted case. Query parameters are derived from here.

        Returns
        -------
        List[Evidence]
            New evidence produced by the provider query, normalized by Phase C.
        VerificationRejection
            If the query cannot be executed or fails.
        """
        if hypothesis.disposition == InvestigationDisposition.INVESTIGATION_EXHAUSTED:
            return VerificationRejection(
                reason=VerificationRejectionReason.EXHAUSTED,
                detail="Agent declared investigation exhausted.",
                hypothesis=hypothesis,
            )

        intent = hypothesis.verification_intent

        try:
            if intent == VerificationIntent.QUERY_PROVIDER_REFUND:
                return await self._query_provider_refund(case)
            elif intent == VerificationIntent.QUERY_PROVIDER_PAYMENT:
                return await self._query_provider_payment(case)
            elif intent == VerificationIntent.QUERY_REFUND_EVENTS:
                return await self._query_refund_events(case)
            else:
                return VerificationRejection(
                    reason=VerificationRejectionReason.EXHAUSTED,
                    detail=f"Unsupported verification intent: {intent}",
                    hypothesis=hypothesis,
                )
        except httpx.HTTPError as exc:
            return VerificationRejection(
                reason=VerificationRejectionReason.PROVIDER_ERROR,
                detail=f"Provider network/API error: {exc}",
                hypothesis=hypothesis,
            )
        except Exception as exc:
            return VerificationRejection(
                reason=VerificationRejectionReason.PROVIDER_ERROR,
                detail=f"Unexpected verification failure: {exc}",
                hypothesis=hypothesis,
            )

    async def _query_provider_refund(self, case: ReconciliationCase) -> VerificationResult:
        """
        Query the provider for refunds matching the case expectation's receipt/intent_id.
        """
        if not case.expectation:
            return VerificationRejection(
                reason=VerificationRejectionReason.EXHAUSTED,
                detail="Cannot query provider refund: case has no expected refund.",
            )

        payment_id = case.expectation.provider_payment_id
        receipt = case.expectation.intent_id

        if not payment_id or not receipt:
            return VerificationRejection(
                reason=VerificationRejectionReason.EXHAUSTED,
                detail="Cannot query provider refund: missing payment_id or intent_id.",
            )

        # Execute read-only provider call using only trusted parameters
        refunds = await self._client.get_payment_refunds(payment_id)

        # Filter to the specific receipt we care about
        matched = [r for r in refunds if r.receipt == receipt]

        evidences: List[Evidence] = []
        for r in matched:
            evidence = self._normalizer.normalize(
                raw_payload=r.model_dump(),
                provenance={
                    "source": "verifier_query",
                    "intent": VerificationIntent.QUERY_PROVIDER_REFUND.value,
                },
            )
            evidences.append(evidence)

        return evidences

    async def _query_provider_payment(self, case: ReconciliationCase) -> VerificationResult:
        """
        Query the provider for the parent payment state.
        """
        if not case.expectation or not case.expectation.provider_payment_id:
            return VerificationRejection(
                reason=VerificationRejectionReason.EXHAUSTED,
                detail="Cannot query provider payment: missing provider_payment_id.",
            )

        payment_id = case.expectation.provider_payment_id

        # Execute read-only provider call using only trusted parameters
        payment = await self._client.get_payment(payment_id)

        evidence = self._normalizer.normalize(
            raw_payload=payment.model_dump(),
            provenance={
                "source": "verifier_query",
                "intent": VerificationIntent.QUERY_PROVIDER_PAYMENT.value,
            },
        )
        return [evidence]

    async def _query_refund_events(self, case: ReconciliationCase) -> VerificationResult:
        """
        For now, this executes the same underlying query as QUERY_PROVIDER_REFUND
        and returns all matching evidence.
        """
        return await self._query_provider_refund(case)
