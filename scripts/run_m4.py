import sys
import os
import argparse
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.reconciliation.models import VerifiedDiscrepancy
from src.investigation.config import LLMConfig
from src.investigation.ai import InvestigationEngine
from src.investigation.evidence import MockEvidenceGatherer
from src.investigation.orchestrator import InvestigationOrchestrator
from src.investigation.reporter import InvestigationReporter
from tests.evaluation.corpus import EVALUATION_CORPUS

def main():
    parser = argparse.ArgumentParser(description="Run the M4 Investigation Pipeline")
    parser.add_argument("--model", type=str, default="phi4-mini:3.8b-q4_K_M", help="LLM model name to use")
    parser.add_argument("--case", type=str, default="01", help="Case ID to run from the evaluation corpus")
    args = parser.parse_args()

    # Find the requested case to mock M3
    case = next((c for c in EVALUATION_CORPUS if c.case_id == args.case), None)
    if not case:
        print(f"Error: Case {args.case} not found in evaluation corpus.")
        sys.exit(1)

    # 1. M3 deterministic verification produces VerifiedDiscrepancy
    discrepancy = VerifiedDiscrepancy(
        discrepancy_id=case.case_id,
        description=case.description,
        provider_status=case.discrepancy.provider_status,
        merchant_status=case.discrepancy.merchant_status,
        amount_match=case.discrepancy.amount_match,
        currency_match=case.discrepancy.currency_match,
        identity_verified=case.discrepancy.identity_verified
    )

    # 2. Map evaluation evidence to engine EvidenceItem, typing content where applicable
    from src.investigation.models import EvidenceItem, EvidenceType, WebhookCapturedContent, ProcessingCoverageContent
    
    mapped_evidence = []
    for ev in case.evidence:
        content = ev.content
        if ev.type == EvidenceType.E_WEBHOOK_CAPTURED:
            content = WebhookCapturedContent(present=ev.content.get("present", False))
        elif ev.type == EvidenceType.E_PROCESSING_COVERAGE:
            content = ProcessingCoverageContent(
                coverage=ev.content.get("coverage", "UNKNOWN"),
                processing_count=ev.content.get("processing_count", 0)
            )
            
        mapped_evidence.append(EvidenceItem(
            id=ev.id,
            type=EvidenceType(ev.type.value),
            content=content
        ))

    # 3. Setup Evidence Gatherer (Mocked with the evaluation corpus evidence)
    gatherer = MockEvidenceGatherer(mock_evidence=mapped_evidence)

    # 3. Configure LLM
    config = LLMConfig(model_name=args.model)
    engine = InvestigationEngine(config=config)

    # 4. Initialize Orchestrator
    orchestrator = InvestigationOrchestrator(engine=engine, gatherer=gatherer)

    # 5. Run Investigation
    print(f"Starting investigation for Case {args.case} using {args.model}...")
    result = orchestrator.investigate(discrepancy)

    # 6. Generate and print report
    report = InvestigationReporter.generate_operator_report(result)
    print("\n" + report)

if __name__ == "__main__":
    main()
