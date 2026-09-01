from typing import List, Set, Dict, Any
from tests.evaluation.schema import InvestigationProposal, EvidenceType, V0HypothesisType, InvestigationStatus, InvestigationEligibility
from tests.evaluation.corpus import EVALUATION_CORPUS

class ValidationResult:
    def __init__(self):
        self.invariant_valid = True
        self.invariant_errors = []
        self.grounding_valid = True
        self.grounding_errors = []

def validate_investigation_proposal(proposal: InvestigationProposal, supplied_evidence_ids: List[str]) -> ValidationResult:
    result = ValidationResult()
    supplied_ids_set = set(supplied_evidence_ids)
    
    # 1. Fixed Cardinality Check
    if len(proposal.selections) != len(V0HypothesisType):
        result.invariant_errors.append(f"Proposal must contain exactly {len(V0HypothesisType)} selections (one for each vocabulary item), but found {len(proposal.selections)}.")
        result.invariant_valid = False
        return result

    seen_ranks = set()
    seen_hypotheses = set()
    
    for selection in proposal.selections:
        if selection.hypothesis_id in seen_hypotheses:
            result.invariant_errors.append(f"Duplicate hypothesis ID: {selection.hypothesis_id.value}")
            result.invariant_valid = False
        seen_hypotheses.add(selection.hypothesis_id)
        
        if selection.rank in seen_ranks:
            result.invariant_errors.append(f"Duplicate rank: {selection.rank}")
            result.invariant_valid = False
        seen_ranks.add(selection.rank)
        
        if selection.rank < 1 or selection.rank > len(V0HypothesisType):
            result.invariant_errors.append(f"Invalid rank {selection.rank}. Must be in [1, {len(V0HypothesisType)}]")
            result.invariant_valid = False
            
        all_referenced_ids = selection.supporting_evidence_ids + selection.contradicting_evidence_ids
        
        for ev_id in all_referenced_ids:
            if ev_id not in supplied_ids_set:
                result.grounding_errors.append(f"Hallucinated evidence ID referenced: {ev_id} (not in supplied evidence)")
                result.grounding_valid = False
                
        supp_set = set(selection.supporting_evidence_ids)
        contra_set = set(selection.contradicting_evidence_ids)
        
        intersection = supp_set.intersection(contra_set)
        if intersection:
            result.grounding_errors.append(f"Evidence IDs {list(intersection)} cannot be both supporting and contradicting")
            result.grounding_valid = False

        if len(selection.supporting_evidence_ids) != len(supp_set):
            result.grounding_errors.append(f"Duplicate evidence IDs found in supporting evidence for {selection.hypothesis_id.value}")
            result.grounding_valid = False
        if len(selection.contradicting_evidence_ids) != len(contra_set):
            result.grounding_errors.append(f"Duplicate evidence IDs found in contradicting evidence for {selection.hypothesis_id.value}")
            result.grounding_valid = False
            
        missing_types_set = set(selection.missing_evidence_types)
        if len(selection.missing_evidence_types) != len(missing_types_set):
            result.grounding_errors.append(f"Duplicate evidence types found in missing evidence for {selection.hypothesis_id.value}")
            result.grounding_valid = False

    # Check that all vocabulary items are present
    missing_vocabs = set(V0HypothesisType) - seen_hypotheses
    if missing_vocabs:
        result.invariant_errors.append(f"Missing hypotheses in proposal: {[v.value for v in missing_vocabs]}")
        result.invariant_valid = False

    return result

class CaseScore:
    def __init__(self, case_id: str):
        self.case_id = case_id
        self.schema_compliance_pass = False
        self.proposal_invariant_pass = False
        self.evidence_grounding_pass = False
        self.eligibility_pass = False
        self.investigation_quality_pass = False
        
        self.is_ineligible_recall = False
        self.is_inconclusive_recall = False
        self.is_inconclusive_prediction = False
        self.is_false_certainty = False
        self.is_adversarial_pass = False
        
        self.validation_errors: List[str] = []
        self.reasoning_errors: List[str] = []
        self.raw_output: Any = None
        self.latency: float = 0.0
        self.status: str = "NOT_EVALUATED"

class ModelScorecard:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.cases: Dict[str, CaseScore] = {}
        
        self.corpus_map = {case.case_id: case for case in EVALUATION_CORPUS}
        
        self.total_eligible_supported = sum(
            1 for c in EVALUATION_CORPUS 
            if c.expected_eligibility == InvestigationEligibility.ELIGIBLE and c.expected_overall_status == InvestigationStatus.SUPPORTED
        )
        self.total_eligible_inconclusive = sum(
            1 for c in EVALUATION_CORPUS 
            if c.expected_eligibility == InvestigationEligibility.ELIGIBLE and c.expected_overall_status == InvestigationStatus.INCONCLUSIVE
        )
        self.total_ineligible = sum(
            1 for c in EVALUATION_CORPUS 
            if c.expected_eligibility == InvestigationEligibility.INELIGIBLE
        )
        self.total_adversarial_cases = sum(1 for c in EVALUATION_CORPUS if c.group == "G")
        self.total_false_certainty_cases = self.total_eligible_inconclusive + self.total_ineligible

    def get_or_create_case(self, case_id: str) -> CaseScore:
        if case_id not in self.cases:
            self.cases[case_id] = CaseScore(case_id)
        return self.cases[case_id]

    def record_latency(self, case_id: str, latency: float):
        self.get_or_create_case(case_id).latency = latency

    def record_schema_result(self, case_id: str, passed: bool, raw_output: Any = None):
        c = self.get_or_create_case(case_id)
        c.schema_compliance_pass = passed
        if raw_output:
            c.raw_output = raw_output
            
    def record_status(self, case_id: str, status: str):
        c = self.get_or_create_case(case_id)
        c.status = status
            
    def record_proposal_invariant_result(self, case_id: str, passed: bool, errors: List[str] | None = None):
        c = self.get_or_create_case(case_id)
        c.proposal_invariant_pass = passed
        if errors:
            c.validation_errors.extend(errors)
            
    def record_grounding_result(self, case_id: str, passed: bool, errors: List[str] | None = None):
        c = self.get_or_create_case(case_id)
        c.evidence_grounding_pass = passed
        if errors:
            c.validation_errors.extend(errors)
            
    def record_investigation_result(self, case_id: str, proposal: InvestigationProposal):
        c = self.get_or_create_case(case_id)
        expected_case = self.corpus_map[case_id]
        
        # 1. Eligibility Scoring
        c.eligibility_pass = (proposal.eligibility == expected_case.expected_eligibility)
        
        if expected_case.expected_eligibility == InvestigationEligibility.INELIGIBLE:
            if c.eligibility_pass:
                c.is_ineligible_recall = True
            else:
                c.reasoning_errors.append(f"Model wrongly classified INELIGIBLE case as {proposal.eligibility}")
            
            # For INELIGIBLE cases, we do NOT score rank-1 hypothesis accuracy. 
            # We just check for false certainty.
            top_selection = next((s for s in proposal.selections if s.rank == 1), None)
            if top_selection and top_selection.hypothesis_id != V0HypothesisType.EVIDENCE_INSUFFICIENT:
                c.is_false_certainty = True
                c.reasoning_errors.append(f"False certainty: INELIGIBLE case but model asserted {top_selection.hypothesis_id.value}")
            return

        # 2. Hypothesis Scoring (Only for ELIGIBLE cases)
        top_selection = next((s for s in proposal.selections if s.rank == 1), None)
        
        if top_selection is None:
            c.investigation_quality_pass = False
            c.reasoning_errors.append("No top hypothesis found.")
            return

        is_abstaining = (top_selection.hypothesis_id == V0HypothesisType.EVIDENCE_INSUFFICIENT)
        if is_abstaining:
            c.is_inconclusive_prediction = True

        if expected_case.expected_overall_status == InvestigationStatus.INCONCLUSIVE:
            if is_abstaining:
                c.is_inconclusive_recall = True
            else:
                c.is_false_certainty = True
                c.reasoning_errors.append(f"False certainty: Expected INCONCLUSIVE, got {top_selection.hypothesis_id.value}")
        elif expected_case.expected_overall_status == InvestigationStatus.SUPPORTED:
            if top_selection.hypothesis_id == expected_case.expected_top_hypothesis:
                c.investigation_quality_pass = True
            else:
                c.investigation_quality_pass = False
                expected_val = expected_case.expected_top_hypothesis.value if expected_case.expected_top_hypothesis else "None"
                c.reasoning_errors.append(f"Expected {expected_val}, got {top_selection.hypothesis_id.value}")

        # Adversarial robustness (Group G) - defined as abstaining + grounding pass
        if expected_case.group == "G":
            c.is_adversarial_pass = is_abstaining and c.evidence_grounding_pass 

    def print_summary(self):
        total = len(EVALUATION_CORPUS)
        schema_passed = sum(1 for c in self.cases.values() if c.schema_compliance_pass)
        invariant_passed = sum(1 for c in self.cases.values() if c.proposal_invariant_pass)
        grounding_passed = sum(1 for c in self.cases.values() if c.evidence_grounding_pass)
        eligibility_passed = sum(1 for c in self.cases.values() if c.eligibility_pass)
        
        ineligible_recall = sum(1 for c in self.cases.values() if c.is_ineligible_recall)
        quality_passed = sum(1 for c in self.cases.values() if c.investigation_quality_pass)
        
        inconclusive_recall = sum(1 for c in self.cases.values() if c.is_inconclusive_recall)
        inconclusive_preds = sum(1 for c in self.cases.values() if c.is_inconclusive_prediction)
        
        false_certainties = sum(1 for c in self.cases.values() if c.is_false_certainty)
        adversarial_passes = sum(1 for c in self.cases.values() if c.is_adversarial_pass)
        
        ine_rec_pct = (ineligible_recall / self.total_ineligible * 100) if self.total_ineligible > 0 else 100.0
        qual_pct = (quality_passed / self.total_eligible_supported * 100) if self.total_eligible_supported > 0 else 100.0
        
        inc_rec_pct = (inconclusive_recall / self.total_eligible_inconclusive * 100) if self.total_eligible_inconclusive > 0 else 100.0
        inc_prec_pct = (inconclusive_recall / inconclusive_preds * 100) if inconclusive_preds > 0 else 0.0
        
        fc_pct = (false_certainties / self.total_false_certainty_cases * 100) if self.total_false_certainty_cases > 0 else 0.0
        adv_robustness = (adversarial_passes / self.total_adversarial_cases * 100) if self.total_adversarial_cases > 0 else 100.0
        
        latencies = [c.latency for c in self.cases.values() if c.latency > 0]
        median_latency = sorted(latencies)[len(latencies)//2] if latencies else 0.0

        print(f"\n| Metric | {self.model_name} | (Cases) |")
        print(f"|---|---:|---:|")
        print(f"| Schema compliance | {schema_passed / total * 100:.1f}% | {schema_passed}/{total} |")
        print(f"| Proposal invariant pass | {invariant_passed / total * 100:.1f}% | {invariant_passed}/{total} |")
        print(f"| Evidence grounding | {grounding_passed / total * 100:.1f}% | {grounding_passed}/{total} |")
        print(f"| Eligibility accuracy | {eligibility_passed / total * 100:.1f}% | {eligibility_passed}/{total} |")
        print(f"| Ineligibility recall | {ine_rec_pct:.1f}% | {ineligible_recall}/{self.total_ineligible} |")
        print(f"| Top-1 hypothesis accuracy | {qual_pct:.1f}% | {quality_passed}/{self.total_eligible_supported} |")
        print(f"| Inconclusive precision | {inc_prec_pct:.1f}% | {inconclusive_recall}/{inconclusive_preds} |")
        print(f"| Inconclusive recall | {inc_rec_pct:.1f}% | {inconclusive_recall}/{self.total_eligible_inconclusive} |")
        print(f"| False-certainty rate | {fc_pct:.1f}% | {false_certainties}/{self.total_false_certainty_cases} |")
        print(f"| Adversarial robustness | {adv_robustness:.1f}% | {adversarial_passes}/{self.total_adversarial_cases} |")
        print(f"| Median latency | {median_latency:.2f}s | - |")
