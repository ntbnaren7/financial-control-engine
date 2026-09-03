from typing import Protocol, List
import hashlib
import json
from datetime import datetime, timezone
import uuid

from src.domain.investigation.models import VerificationIntent, VerificationResult, VerificationStatus, VerificationRejectionReason
from src.domain.investigation.context import InvestigationContext
from src.domain.core.models import Evidence
from src.integrations.razorpay.client import RazorpayClient, ProviderNetworkError, ProviderClientError
from src.integrations.razorpay.normalizer import RazorpayV2Normalizer

class ProviderVerifier(Protocol):
    async def verify(self, intent: VerificationIntent, context: InvestigationContext) -> VerificationResult:
        """Executes a read-only provider query and returns the verification result."""
        ...

class RazorpayVerifier:
    def __init__(self, client: RazorpayClient):
        self._client = client

    async def verify(self, intent: VerificationIntent, context: InvestigationContext) -> VerificationResult:
        if intent == VerificationIntent.QUERY_PROVIDER_STATE or intent == VerificationIntent.QUERY_PROVIDER_TRANSACTION:
            return await self._query_provider_state(intent, context)
        
        return VerificationResult(
            verification_id=str(uuid.uuid4()),
            intent=intent,
            status=VerificationStatus.REJECTED,
            evidence_ids=[],
            new_evidence=[],
            new_observations=[],
            failure_reason=f"Unsupported intent {intent} for Razorpay",
            verified_at=datetime.now(timezone.utc)
        )

    async def _query_provider_state(self, intent: VerificationIntent, context: InvestigationContext) -> VerificationResult:
        provider_ref = None
        internal_ref = None
        
        if context.expectation:
            provider_ref = context.expectation.correlation_keys.provider_ref
            internal_ref = context.expectation.correlation_keys.internal_ref
            
        if not provider_ref and context.observations:
            provider_ref = context.observations[0].correlation_keys.provider_ref
            
        if not provider_ref:
            return VerificationResult(
                verification_id=str(uuid.uuid4()),
                intent=intent,
                status=VerificationStatus.REJECTED,
                evidence_ids=[],
                new_evidence=[],
                new_observations=[],
                failure_reason=VerificationRejectionReason.MISSING_PARAMETERS.value,
                verified_at=datetime.now(timezone.utc)
            )

        try:
            refunds = await self._client.get_payment_refunds(provider_ref)
        except ProviderClientError as e:
            return VerificationResult(
                verification_id=str(uuid.uuid4()),
                intent=intent,
                status=VerificationStatus.REJECTED,
                evidence_ids=[],
                new_evidence=[],
                new_observations=[],
                failure_reason=str(e),
                verified_at=datetime.now(timezone.utc)
            )
        except ProviderNetworkError as e:
            return VerificationResult(
                verification_id=str(uuid.uuid4()),
                intent=intent,
                status=VerificationStatus.FAILED,
                evidence_ids=[],
                new_evidence=[],
                new_observations=[],
                failure_reason=str(e),
                verified_at=datetime.now(timezone.utc)
            )

        evidence_ids = []
        new_evidence = []
        new_obs = []
        now = datetime.now(timezone.utc)
        
        for r in refunds:
            if internal_ref and r.receipt != internal_ref:
                continue

            payload = r.model_dump()
            payload_bytes = json.dumps(payload, sort_keys=True).encode()
            
            ev = Evidence(
                source="razorpay_api",
                source_reference=f"refund_{r.id}",
                payload_hash=hashlib.sha256(payload_bytes).hexdigest(),
                raw_payload_ref=f"s3://evidence/razorpay/{r.id}",
                observed_at=now
            )
            evidence_ids.append(ev.evidence_id)
            new_evidence.append(ev)
            
            obs = RazorpayV2Normalizer.normalize_refund(payload, ev.evidence_id)
            new_obs.append(obs)

        return VerificationResult(
            verification_id=str(uuid.uuid4()),
            intent=intent,
            status=VerificationStatus.SUCCEEDED,
            evidence_ids=evidence_ids,
            new_evidence=new_evidence,
            new_observations=new_obs,
            verified_at=now
        )
