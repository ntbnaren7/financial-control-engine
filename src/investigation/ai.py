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
        example = {
            "eligibility": "ELIGIBLE",
            "overall_confidence": "MEDIUM",
            "selections": [
                {
                    "hypothesis_id": "WEBHOOK_OBSERVED_NOT_PROCESSED",
                    "rank": 1,
                    "rationale": "Webhook observation exists but no processing record found under COMPLETE coverage.",
                    "confidence_band": "MEDIUM",
                    "supporting_evidence_ids": ["EV-WH-001"],
                    "contradicting_evidence_ids": [],
                    "missing_evidence_types": ["E_MERCHANT_PROCESSING"]
                },
                {
                    "hypothesis_id": "WEBHOOK_NOT_OBSERVED",
                    "rank": 2,
                    "rationale": "Not supported — webhook observation record is present.",
                    "confidence_band": "LOW",
                    "supporting_evidence_ids": [],
                    "contradicting_evidence_ids": ["EV-WH-001"],
                    "missing_evidence_types": []
                },
                {
                    "hypothesis_id": "WEBHOOK_PROCESSED_STATE_NOT_UPDATED",
                    "rank": 3,
                    "rationale": "No processing record exists, so state update failure is unlikely.",
                    "confidence_band": "LOW",
                    "supporting_evidence_ids": [],
                    "contradicting_evidence_ids": ["EV-PC-001"],
                    "missing_evidence_types": []
                },
                {
                    "hypothesis_id": "PROVIDER_MERCHANT_STATE_REPRESENTATION_MISMATCH",
                    "rank": 4,
                    "rationale": "Processing chain failure observed; representation mismatch is unlikely to be the cause.",
                    "confidence_band": "LOW",
                    "supporting_evidence_ids": [],
                    "contradicting_evidence_ids": [],
                    "missing_evidence_types": []
                },
                {
                    "hypothesis_id": "EVIDENCE_INSUFFICIENT",
                    "rank": 5,
                    "rationale": "Evidence is sufficient to distinguish the primary hypothesis in this case.",
                    "confidence_band": "LOW",
                    "supporting_evidence_ids": [],
                    "contradicting_evidence_ids": [],
                    "missing_evidence_types": []
                }
            ]
        }

        return (
            "You are an investigation assistant for a financial control engine.\n"
            "Analyze the provided discrepancy and evidence, and rank the five causal hypotheses.\n\n"

            "## Reasoning Contract\n\n"
            "Reason over the observed event sequence. A hypothesis may be ranked highly only when "
            "its supporting conditions are backed by authoritative evidence.\n\n"
            "**Critical epistemic rules:**\n"
            "- Absence of an observation is NOT evidence of absence unless coverage is explicitly "
            "COMPLETE. If coverage is UNKNOWN or PARTIAL, a missing record means the evidence is "
            "inconclusive, not that the event did not occur.\n"
            "- Do NOT select a hypothesis merely because its downstream consequence resembles the "
            "observed discrepancy. Select the hypothesis directly consistent with the observed "
            "event sequence.\n"
            "- Do NOT select a hypothesis whose disqualifying conditions are present in the evidence.\n"
            "- If you cannot sufficiently distinguish the cause from the available evidence — even "
            "with significant evidence present — rank EVIDENCE_INSUFFICIENT at position 1.\n\n"

            "## Hypothesis Definitions\n\n"
            "You MUST rank all five hypotheses. The following definitions specify what each "
            "hypothesis means, what conditions support it, and what conditions disqualify it.\n\n"
            f"{hypothesis_block}"

            "## Required Output Format\n\n"
            "Output ONLY a raw JSON object. Do NOT output a schema or schema description. "
            "Do NOT output markdown code blocks. Output ONLY the filled-in JSON.\n\n"
            "Here is an example of a valid response (with placeholder values — "
            "you MUST fill in your own analysis):\n"
            f"{json.dumps(example, indent=2)}\n\n"

            "## Output Rules\n"
            "- eligibility: must be 'ELIGIBLE' or 'INELIGIBLE'.\n"
            "- overall_confidence: must be 'HIGH', 'MEDIUM', or 'LOW'.\n"
            "- selections: EXACTLY 5 entries, one per hypothesis, ranked 1 (most likely) to 5 (least likely). No duplicate ranks.\n"
            "- hypothesis_id: must be one of the five V0HypothesisType values shown above.\n"
            "- Do not invent evidence IDs. Use only IDs from the supplied evidence list.\n"
            "- confidence_band: must be 'HIGH', 'MEDIUM', or 'LOW'.\n"
            "- Do not output markdown, code fences, or commentary. Raw JSON only."
        )

    def _build_user_prompt(self, context: DiscrepancyContext, evidence: List[EvidenceItem]) -> str:
        prompt = (
            f"Case Description: {context.description}\n"
            f"Discrepancy: {context.model_dump_json()}\n"
            f"Supplied Evidence:\n"
        )
        for ev in evidence:
            content_str = ev.content.model_dump_json() if hasattr(ev.content, "model_dump_json") else json.dumps(ev.content)
            prompt += f"- ID: {ev.id}, Type: {ev.type.value}, Content: {content_str}\n"
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
