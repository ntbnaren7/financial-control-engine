import asyncio
from typing import Optional, Dict
from src.domain.investigation.models import CausalHypothesis, InvestigationDisposition, VerificationIntent

class SyntheticInvestigator:
    def __init__(self, fallback_investigator, sub_case_hints: Dict[str, str]):
        self._fallback = fallback_investigator
        self._hints = sub_case_hints

    def _get_hint_for_case(self, agent_input: dict) -> str:
        try:
            expected_refund = agent_input.get("expected_refund")
            if not expected_refund:
                return ""
            return self._hints.get(expected_refund.get("intent_id"), "")
        except Exception:
            return ""

    def investigate(self, agent_input: dict) -> CausalHypothesis:
        hint = self._get_hint_for_case(agent_input)

        if hint == "C5_BOUNDARY_REJECT":
            return CausalHypothesis(
                hypothesis="Hypothesis referencing a fabricated evidence ID.",
                supporting_evidence_ids=["hallucinated_evidence_ref_999"],
                contradicting_evidence_ids=[],
                missing_evidence_description="None",
                confidence="LOW",
                disposition=InvestigationDisposition.VERIFICATION_PROPOSED,
                verification_intent=VerificationIntent.QUERY_PROVIDER_REFUND,
            )
        
        if self._fallback:
            try:
                return self._fallback.investigate(agent_input)
            except Exception:
                pass

        return CausalHypothesis(
            hypothesis="Provider status unknown; issuing query to establish execution state.",
            supporting_evidence_ids=[],
            contradicting_evidence_ids=[],
            missing_evidence_description="Provider refund record",
            confidence="LOW",
            disposition=InvestigationDisposition.VERIFICATION_PROPOSED,
            verification_intent=VerificationIntent.QUERY_PROVIDER_REFUND,
        )
