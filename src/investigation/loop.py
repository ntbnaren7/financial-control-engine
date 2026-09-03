"""
V2-A3 — Investigation Orchestrator

The deterministic orchestrator for the investigative agent.
Responsible strictly for sequencing components. It must never interpret
the LLM's hypothesis, nor resolve the financial state itself.

For V2-A3, the orchestrator stops immediately after output validation.
Deterministic verification and policy resolution are deferred to later milestones.
"""

from typing import Union, List

from src.domain.investigation.context import InvestigationContext
from src.domain.investigation.models import CausalHypothesis, ValidationRejection, VerificationResult
from src.investigation.agent import Investigator
from src.investigation.input_formatter import format_context_for_investigation
from src.investigation.validator import OutputValidator
from src.investigation.verifier import DeterministicVerifier


class V2InvestigationOrchestrator:
    """
    Orchestrates a single investigation cycle.
    """

    def __init__(
        self,
        investigator: Investigator,
        validator: OutputValidator,
        verifier: DeterministicVerifier,
    ) -> None:
        self._investigator = investigator
        self._validator = validator
        self._verifier = verifier

    async def investigate(
        self,
        context: InvestigationContext,
    ) -> Union[List[VerificationResult], ValidationRejection]:
        """
        Run exactly one cycle of investigation and verification for an InvestigationContext.
        
        Returns:
            List[VerificationResult] if generation, validation, and verification attempts succeed.
            ValidationRejection if the LLM output violates constraints.
        """
        # 1. Format input for LLM (A3 Context Formatter)
        formatted_input = format_context_for_investigation(context)

        # 2. LLM Hypothesis Generation (A3 Investigator)
        import inspect
        import asyncio
        if inspect.iscoroutinefunction(self._investigator.investigate):
            hypothesis = await self._investigator.investigate(formatted_input)
        else:
            hypothesis = await asyncio.to_thread(self._investigator.investigate, formatted_input)

        # 3. Gatekeeper Validation (A3 Validator)
        validation_result = self._validator.validate(
            hypothesis.model_dump(mode="json"), formatted_input
        )
        
        if isinstance(validation_result, ValidationRejection):
            return validation_result

        # 4. Deterministic Verification (A4 Verifier)
        verification_results = await self._verifier.verify(validation_result, context)
        
        return verification_results
