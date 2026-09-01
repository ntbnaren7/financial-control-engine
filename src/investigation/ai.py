import json
import time
from typing import List
from pydantic import ValidationError
from openai import AsyncOpenAI

from src.investigation.models import (
    DiscrepancyContext,
    EvidenceItem,
    InvestigationProposal,
    HYPOTHESIS_DEFINITIONS,
)
from src.investigation.result import InvestigationResult, InvestigationStatus
from src.investigation.validator import validate_proposal_invariants
from src.investigation.config import LLMConfig

class InvestigationEngine:
    def __init__(self, config: LLMConfig):
        self.config = config
        
        self.client = AsyncOpenAI(
            base_url=self.config.base_url,
            api_key=self.config.api_key
        )

    def _build_hypothesis_definitions_block(self) -> str:
        """Renders HYPOTHESIS_DEFINITIONS into a structured prompt block."""
        lines = []
        for defn in HYPOTHESIS_DEFINITIONS.values():
            lines.append(f"### {defn.hypothesis_id.value}")
            lines.append(f"**Meaning:** {defn.meaning}")
            lines.append("**Supporting conditions** (facts that make this hypothesis plausible):")
            for cond in defn.supporting_conditions:
                lines.append(f"  - {cond}")
            lines.append("**Disqualifying conditions** (facts that make this hypothesis impossible):")
            for cond in defn.disqualifying_conditions:
                lines.append(f"  - {cond}")
            lines.append(f"**Uncertainty:** {defn.uncertainty_note}")
            lines.append("")
        return "\n".join(lines)

    def _build_system_prompt(self) -> str:
        hypothesis_block = self._build_hypothesis_definitions_block()
        return (
            "You are an investigation assistant for a financial control engine.\n"
            "Analyze the provided discrepancy and evidence, and rank the five causal hypotheses.\n\n"

            "## Reasoning Contract\n\n"
            "Reason over the observed event sequence. A hypothesis may be ranked highly only when "
            "its supporting conditions are backed by authoritative evidence.\n\n"
            "**Critical epistemic rules:**\n"
            "- Step 1: Check coverage status.\n"
            "  * If any relevant coverage item (e.g. E_WEBHOOK_COVERAGE, E_PROCESSING_COVERAGE, E_STATE_TRANSITION_COVERAGE) has coverage='UNKNOWN' or is absent, "
            "you CANNOT conclude a specific event failure occurred (absence of record is inconclusive) -> You MUST rank EVIDENCE_INSUFFICIENT at 1.\n"
            "- Step 2: If coverage is COMPLETE, examine the observed event sequence:\n"
            "  * If no webhook observation is present and E_WEBHOOK_COVERAGE shows count 0 with COMPLETE coverage -> rank WEBHOOK_NOT_OBSERVED at 1.\n"
            "  * If webhook is present (E_WEBHOOK_CAPTURED) but E_PROCESSING_COVERAGE shows count 0 under COMPLETE coverage -> rank WEBHOOK_OBSERVED_NOT_PROCESSED at 1.\n"
            "  * If webhook is present (E_WEBHOOK_CAPTURED), merchant processing succeeded (E_MERCHANT_PROCESSING status='PROCESSED'), but merchant order is UNPAID and transition count is 0 under COMPLETE coverage -> rank WEBHOOK_PROCESSED_STATE_NOT_UPDATED at 1.\n"
            "  * If all processing and transitions succeeded and states match in business meaning but differ in status label (e.g. 'captured' vs 'SETTLED') -> rank PROVIDER_MERCHANT_STATE_REPRESENTATION_MISMATCH at 1.\n"
            "- Step 3: Consistency checks:\n"
            "  * Do NOT rank WEBHOOK_NOT_OBSERVED at 1 if a webhook observation (E_WEBHOOK_CAPTURED) is present in the evidence list (this is a fatal contradiction).\n"
            "  * Do NOT select a hypothesis whose disqualifying conditions are present in the evidence.\n\n"
            "- Do NOT select a hypothesis merely because its downstream consequence resembles the "
            "observed discrepancy. Select the hypothesis directly consistent with the observed "
            "event sequence.\n"
            "- Do NOT select a hypothesis whose disqualifying conditions are present in the evidence.\n\n"

            "## Hypothesis Definitions\n\n"
            "You MUST rank all five hypotheses. The following definitions specify what each "
            "hypothesis means, what conditions support it, and what conditions disqualify it.\n\n"
            f"{hypothesis_block}"

            "## Required Output Format\n\n"
            "Output ONLY a raw JSON object. Do NOT output markdown code blocks. Output ONLY the filled-in JSON.\n\n"
            "You MUST rank all five hypotheses in 'selections', with ranks 1, 2, 3, 4, and 5.\n"
            "Here is the exact JSON structure required:\n"
            "{\n"
            '  "eligibility": "ELIGIBLE",\n'
            '  "overall_confidence": "HIGH",\n'
            '  "selections": [\n'
            '    {\n'
            '      "hypothesis_id": "<HYPOTHESIS_AT_RANK_1>",\n'
            '      "rank": 1,\n'
            '      "rationale": "<Reason why this is the top hypothesis based on the evidence>",\n'
            '      "confidence_band": "HIGH",\n'
            '      "supporting_evidence_ids": ["<EVIDENCE_ID>"],\n'
            '      "contradicting_evidence_ids": [],\n'
            '      "missing_evidence_types": []\n'
            '    },\n'
            '    {\n'
            '      "hypothesis_id": "<HYPOTHESIS_AT_RANK_2>",\n'
            '      "rank": 2,\n'
            '      "rationale": "<Reason why this is rank 2>",\n'
            '      "confidence_band": "MEDIUM",\n'
            '      "supporting_evidence_ids": [],\n'
            '      "contradicting_evidence_ids": [],\n'
            '      "missing_evidence_types": []\n'
            '    },\n'
            '    {\n'
            '      "hypothesis_id": "<HYPOTHESIS_AT_RANK_3>",\n'
            '      "rank": 3,\n'
            '      "rationale": "<Reason why this is rank 3>",\n'
            '      "confidence_band": "LOW",\n'
            '      "supporting_evidence_ids": [],\n'
            '      "contradicting_evidence_ids": [],\n'
            '      "missing_evidence_types": []\n'
            '    },\n'
            '    {\n'
            '      "hypothesis_id": "<HYPOTHESIS_AT_RANK_4>",\n'
            '      "rank": 4,\n'
            '      "rationale": "<Reason why this is rank 4>",\n'
            '      "confidence_band": "LOW",\n'
            '      "supporting_evidence_ids": [],\n'
            '      "contradicting_evidence_ids": [],\n'
            '      "missing_evidence_types": []\n'
            '    },\n'
            '    {\n'
            '      "hypothesis_id": "<HYPOTHESIS_AT_RANK_5>",\n'
            '      "rank": 5,\n'
            '      "rationale": "<Reason why this is rank 5>",\n'
            '      "confidence_band": "LOW",\n'
            '      "supporting_evidence_ids": [],\n'
            '      "contradicting_evidence_ids": [],\n'
            '      "missing_evidence_types": []\n'
            '    }\n'
            '  ]\n'
            "}\n\n"
            "## Output Rules\n"
            "- eligibility: 'ELIGIBLE' or 'INELIGIBLE'.\n"
            "- overall_confidence: 'HIGH', 'MEDIUM', or 'LOW'.\n"
            "- selections: EXACTLY 5 entries. You MUST include each of the 5 hypotheses with unique ranks 1 to 5: "
            "WEBHOOK_NOT_OBSERVED, WEBHOOK_OBSERVED_NOT_PROCESSED, WEBHOOK_PROCESSED_STATE_NOT_UPDATED, "
            "PROVIDER_MERCHANT_STATE_REPRESENTATION_MISMATCH, EVIDENCE_INSUFFICIENT.\n"
            "- supporting_evidence_ids / contradicting_evidence_ids: Use only IDs from the supplied evidence packet.\n"
            "- missing_evidence_types: Leave as empty list [] unless requesting specific EvidenceType names.\n"
            "- confidence_band: 'HIGH', 'MEDIUM', or 'LOW'.\n"
            "- Raw JSON only."
        )

    def _build_user_prompt(self, context: DiscrepancyContext, evidence: List[EvidenceItem]) -> str:
        prompt = (
            f"Case: {context.case_id}\n"
            f"Discrepancy Description: {context.description}\n"
            f"- Provider Status: {context.provider_status}\n"
            f"- Merchant Status: {context.merchant_status}\n"
            f"- Amount Match: {context.amount_match}\n"
            f"- Currency Match: {context.currency_match}\n"
            f"- Identity Verified: {context.identity_verified}\n\n"
            f"Supplied Evidence Packet ({len(evidence)} items):\n"
        )
        for ev in evidence:
            content_str = ev.content.model_dump_json(exclude_none=True) if hasattr(ev.content, "model_dump_json") else json.dumps(ev.content)
            prompt += f"- [{ev.id}] {ev.type.value}: {content_str}\n"
        return prompt

    async def investigate(self, context: DiscrepancyContext, evidence: List[EvidenceItem]) -> InvestigationResult:
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(context, evidence)
        supplied_ids = [ev.id for ev in evidence]
        
        start_time = time.time()
        
        try:
            response = await self.client.chat.completions.create(
                model=self.config.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"},
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                extra_body={"num_ctx": self.config.num_ctx}
            )
            raw_output = response.choices[0].message.content or ""
        except Exception as e:
            latency = time.time() - start_time
            return InvestigationResult(
                status=InvestigationStatus.API_ERROR,
                failure_reason=str(e),
                latency_seconds=latency
            )
            
        latency = time.time() - start_time
        
        # Harden parser: strip <think> blocks safely and extract JSON
        import re
        clean_output = re.sub(r'(?s)<think>.*?</think>', '', raw_output)
        
        start_idx = clean_output.find('{')
        end_idx = clean_output.rfind('}')
        if start_idx != -1 and end_idx != -1:
            clean_output = clean_output[start_idx:end_idx+1]
        else:
            clean_output = clean_output.strip()

        if not clean_output:
            return InvestigationResult(
                status=InvestigationStatus.EMPTY_OUTPUT,
                failure_reason="Model returned empty output after parsing.",
                latency_seconds=latency,
                raw_output=raw_output
            )
            
        try:
            parsed_json = json.loads(clean_output)
        except json.JSONDecodeError as e:
            return InvestigationResult(
                status=InvestigationStatus.SCHEMA_INVALID,
                failure_reason=f"INVALID_JSON: {str(e)}",
                latency_seconds=latency,
                raw_output=raw_output
            )

        try:
            proposal = InvestigationProposal.model_validate(parsed_json)
        except ValidationError as e:
            return InvestigationResult(
                status=InvestigationStatus.SCHEMA_INVALID,
                failure_reason=f"SCHEMA_INVALID: {str(e)}",
                latency_seconds=latency,
                raw_output=raw_output
            )
            
        validation_result = validate_proposal_invariants(proposal, supplied_ids)
        
        if not validation_result.is_valid:
            return InvestigationResult(
                status=InvestigationStatus.INVARIANT_INVALID,
                failure_reason=f"INVARIANT_INVALID: {validation_result.errors}",
                latency_seconds=latency,
                raw_output=raw_output,
                proposal=proposal
            )
            
        from src.investigation.semantic import validate_semantic_admissibility
        semantic_result = validate_semantic_admissibility(proposal, evidence)
        
        if not semantic_result.is_admissible:
            return InvestigationResult(
                status=InvestigationStatus.PROPOSAL_SEMANTIC_CONFLICT,
                validation_errors=semantic_result.errors,
                failure_reason="PROPOSAL_SEMANTIC_CONFLICT: Model proposal contradicted authoritative evidence.",
                latency_seconds=latency,
                raw_output=raw_output,
                proposal=proposal
            )
            
        return InvestigationResult(
            status=InvestigationStatus.ACCEPTED,
            proposal=proposal,
            latency_seconds=latency,
            raw_output=raw_output
        )
