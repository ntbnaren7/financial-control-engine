from src.investigation.result import InvestigationResult, InvestigationStatus

class InvestigationReporter:
    """
    Isolates presentation formatting from investigation logic.
    Converts a structured InvestigationResult into a human-readable format.
    """
    
    @staticmethod
    def generate_operator_report(result: InvestigationResult) -> str:
        report = []
        report.append("============================================================")
        report.append("M4 INVESTIGATION REPORT")
        report.append("============================================================")
        
        report.append(f"Status: {result.status.value}")
        report.append(f"Latency: {result.latency_seconds:.2f}s")
        
        if result.status != InvestigationStatus.ACCEPTED:
            report.append("\n--- ADMISSIBILITY: ❌ REJECTED ---")
            if result.status == InvestigationStatus.PROPOSAL_SEMANTIC_CONFLICT:
                report.append("Status: PROPOSAL_SEMANTIC_CONFLICT")
                if result.validation_errors:
                    report.append("Semantic Errors:")
                    for err in result.validation_errors:
                        report.append(f"  - {err}")
            else:
                report.append(f"Reason: {result.failure_reason}")
                
            if not result.proposal:
                if result.raw_output:
                    report.append("\nRaw Model Output:")
                    report.append("-" * 40)
                    report.append(result.raw_output)
                    report.append("-" * 40)
                return "\n".join(report)
        else:
            report.append("\n--- ADMISSIBILITY: ✅ ACCEPTED ---")
            
        proposal = result.proposal
        if not proposal:
            return "\n".join(report)
            
        report.append(f"Eligibility: {proposal.eligibility.value}")
        report.append(f"Overall Confidence: {proposal.overall_confidence.value}")
        
        report.append("\n--- HYPOTHESES ---")
        for selection in sorted(proposal.selections, key=lambda s: s.rank):
            report.append(f"\n[{selection.rank}] {selection.hypothesis_id.value}")
            report.append(f"    Confidence: {selection.confidence_band.value}")
            report.append(f"    Rationale:  {selection.rationale}")
            
            if selection.supporting_evidence_ids:
                report.append(f"    Supporting: {', '.join(selection.supporting_evidence_ids)}")
            if selection.contradicting_evidence_ids:
                report.append(f"    Contradicting: {', '.join(selection.contradicting_evidence_ids)}")
            if selection.missing_evidence_types:
                missing = [m.value for m in selection.missing_evidence_types]
                report.append(f"    Missing: {', '.join(missing)}")
                
        return "\n".join(report)
