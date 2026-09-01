import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import json
import time
import argparse
import statistics
from typing import List, Any
from pydantic import ValidationError

from openai import OpenAI

from tests.evaluation.corpus import EVALUATION_CORPUS
from tests.evaluation.schema import InvestigationProposal
from tests.evaluation.validator import validate_investigation_proposal, ModelScorecard

def run_benchmark(args):
    client = OpenAI(base_url=args.api_base, api_key=args.api_key)
    
    print(f"\nStarting benchmark for model family: {args.family}")
    print(f"Artifact: {args.artifact}")
    print(f"Target endpoint: {args.api_base}")
    print(f"Runs: {args.runs}")
    print("-" * 50)
    
    schema_json = InvestigationProposal.model_json_schema()
    
    system_prompt = (
        "You are an investigation assistant for a financial control engine.\n"
        "Analyze the provided discrepancy and evidence, and propose hypotheses.\n"
        "You MUST output raw JSON matching this schema exactly:\n"
        f"{json.dumps(schema_json, indent=2)}\n\n"
        "Rules:\n"
        "- Do not invent evidence IDs. Use only those provided.\n"
        "- You MUST output exactly 5 hypothesis selections, one for each valid V0HypothesisType.\n"
        "- Rank them from 1 (most likely) to 5 (least likely).\n"
        "- Provide a 'rationale' and 'confidence_band' (HIGH, MEDIUM, LOW) for each.\n"
        "- Do not output markdown code blocks, just raw JSON."
    )
    
    import os
    manifest = {
        "model_family": args.family,
        "exact_artifact": args.artifact,
        "quantization": args.quantization,
        "runtime": args.runtime,
        "runtime_version": os.environ.get("BENCH_OLLAMA_VERSION", args.runtime_version),
        "benchmark_git_commit": os.environ.get("BENCH_GIT_COMMIT", "unknown"),
        "corpus_version": "v1.1",
        "timestamp": os.environ.get("BENCH_TIMESTAMP", time.strftime("%Y-%m-%dT%H:%M:%S%z")),
        "context_length": int(os.environ.get("BENCH_CONTEXT_LENGTH", "8192")),
        "temperature": float(os.environ.get("BENCH_TEMP", "0.0")),
        "max_output_tokens": int(os.environ.get("BENCH_MAX_TOKENS", "2048")),
        "runs": args.runs,
        "seeds": [args.seed + i for i in range(args.runs)],
        "hardware": args.hardware
    }
    
    all_scorecards = []
    
    for run_idx in range(args.runs):
        current_seed = args.seed + run_idx
        print(f"\n=== Run {run_idx + 1}/{args.runs} (Seed: {current_seed}) ===")
        scorecard = ModelScorecard(args.family)
        
        for case in EVALUATION_CORPUS:
            print(f"Evaluating Case {case.case_id}...", end=" ", flush=True)
            
            user_prompt = (
                f"Case Description: {case.description}\n"
                f"Discrepancy: {case.discrepancy.model_dump_json()}\n"
                f"Supplied Evidence:\n"
            )
            for ev in case.evidence:
                user_prompt += f"- ID: {ev.id}, Type: {ev.type.value}, Content: {json.dumps(ev.content)}\n"
                
            supplied_ids = [ev.id for ev in case.evidence]
            
            start_time = time.time()
            
            try:
                response = client.chat.completions.create(
                    model=args.artifact,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=float(os.environ.get("BENCH_TEMP", "0.0")),
                    max_tokens=int(os.environ.get("BENCH_MAX_TOKENS", "2048")),
                    seed=current_seed,
                    extra_body={"num_ctx": int(os.environ.get("BENCH_CONTEXT_LENGTH", "8192"))} 
                )
                raw_output = response.choices[0].message.content or ""
                
                # Robustly extract JSON object ignoring conversational filler, markdown, or <think> blocks
                start_idx = raw_output.find('{')
                end_idx = raw_output.rfind('}')
                if start_idx != -1 and end_idx != -1:
                    raw_output = raw_output[start_idx:end_idx+1]
                else:
                    raw_output = raw_output.strip()
                
            except Exception as e:
                print(f"[ERROR] API Call Failed: {e}")
                scorecard.record_schema_result(case.case_id, False, str(e))
                scorecard.record_status(case.case_id, "API_ERROR")
                continue
                
            latency = time.time() - start_time
            scorecard.record_latency(case.case_id, latency)
            
            if not raw_output:
                print(f"[FAIL Schema] EMPTY_OUTPUT")
                scorecard.record_schema_result(case.case_id, False, raw_output)
                scorecard.record_status(case.case_id, "EMPTY_OUTPUT")
                continue
            
            try:
                parsed_json = json.loads(raw_output)
            except json.JSONDecodeError as e:
                print(f"[FAIL Schema] INVALID_JSON: {e}")
                scorecard.record_schema_result(case.case_id, False, raw_output)
                scorecard.record_status(case.case_id, "INVALID_JSON")
                continue

            try:
                proposal = InvestigationProposal.model_validate(parsed_json)
                scorecard.record_schema_result(case.case_id, True, raw_output)
            except ValidationError as e:
                print(f"[FAIL Schema] SCHEMA_INVALID: {e}")
                scorecard.record_schema_result(case.case_id, False, raw_output)
                scorecard.record_status(case.case_id, "SCHEMA_INVALID")
                continue
                
            validation_result = validate_investigation_proposal(proposal, supplied_ids)
            
            if not validation_result.invariant_valid:
                print(f"[FAIL Invariants] {validation_result.invariant_errors}")
                scorecard.record_proposal_invariant_result(case.case_id, False, validation_result.invariant_errors)
                scorecard.record_status(case.case_id, "INVARIANT_INVALID")
            else:
                scorecard.record_proposal_invariant_result(case.case_id, True)
                
            if not validation_result.grounding_valid:
                print(f"[FAIL Grounding] {validation_result.grounding_errors}")
                scorecard.record_grounding_result(case.case_id, False, validation_result.grounding_errors)
            else:
                scorecard.record_grounding_result(case.case_id, True)

            if not validation_result.invariant_valid:
                # Can't check investigation quality if structural invariants are broken
                continue
            
            scorecard.record_status(case.case_id, "VALID")
            scorecard.record_investigation_result(case.case_id, proposal)
            
            case_score = scorecard.get_or_create_case(case.case_id)
            if case_score.investigation_quality_pass:
                print(f"[PASS] {latency:.2f}s")
            else:
                print(f"[FAIL Quality] {case_score.reasoning_errors}")
                
        all_scorecards.append(scorecard)
        scorecard.print_summary() 

    metrics = None
    if args.runs > 1:
        print("\n" + "="*50)
        print("AGGREGATED RESULTS")
        print("="*50)
        
        metrics = {
            "Schema compliance": [],
            "Proposal invariant pass": [],
            "Evidence grounding": [],
            "Eligibility accuracy": [],
            "Ineligibility recall": [],
            "Top-1 investigation accuracy": [],
            "Inconclusive precision": [],
            "Inconclusive recall": [],
            "False-certainty rate": [],
            "Adversarial robustness": []
        }
        
        total = len(EVALUATION_CORPUS)
        
        for sc in all_scorecards:
            schema = sum(1 for c in sc.cases.values() if c.schema_compliance_pass)
            invariant = sum(1 for c in sc.cases.values() if c.proposal_invariant_pass)
            grounding = sum(1 for c in sc.cases.values() if c.evidence_grounding_pass)
            elig = sum(1 for c in sc.cases.values() if c.eligibility_pass)
            
            ineligible_recall = sum(1 for c in sc.cases.values() if c.is_ineligible_recall)
            quality = sum(1 for c in sc.cases.values() if c.investigation_quality_pass)
            
            inc_recall = sum(1 for c in sc.cases.values() if c.is_inconclusive_recall)
            inc_preds = sum(1 for c in sc.cases.values() if c.is_inconclusive_prediction)
            
            false_certainties = sum(1 for c in sc.cases.values() if c.is_false_certainty)
            adv_passes = sum(1 for c in sc.cases.values() if c.is_adversarial_pass)
            
            ine_rec_pct = (ineligible_recall / sc.total_ineligible * 100) if sc.total_ineligible > 0 else 100.0
            qual_pct = (quality / sc.total_eligible_supported * 100) if sc.total_eligible_supported > 0 else 100.0
            inc_rec_pct = (inc_recall / sc.total_eligible_inconclusive * 100) if sc.total_eligible_inconclusive > 0 else 100.0
            inc_prec_pct = (inc_recall / inc_preds * 100) if inc_preds > 0 else 0.0
            fcr_pct = (false_certainties / sc.total_false_certainty_cases * 100) if sc.total_false_certainty_cases > 0 else 0.0
            adv_rob = (adv_passes / sc.total_adversarial_cases * 100) if sc.total_adversarial_cases > 0 else 100.0
            
            metrics["Schema compliance"].append(schema / total * 100)
            metrics["Proposal invariant pass"].append(invariant / total * 100)
            metrics["Evidence grounding"].append(grounding / total * 100)
            metrics["Eligibility accuracy"].append(elig / total * 100)
            metrics["Ineligibility recall"].append(ine_rec_pct)
            metrics["Top-1 investigation accuracy"].append(qual_pct)
            metrics["Inconclusive precision"].append(inc_prec_pct)
            metrics["Inconclusive recall"].append(inc_rec_pct)
            metrics["False-certainty rate"].append(fcr_pct)
            metrics["Adversarial robustness"].append(adv_rob)
            
        print(f"\n| Metric | Mean | Min | Max |")
        print(f"|---|---:|---:|---:|")
        for metric, values in metrics.items():
            print(f"| {metric} | {statistics.mean(values):.1f}% | {min(values):.1f}% | {max(values):.1f}% |")
            
    os.makedirs("benchmark_results", exist_ok=True)
    safe_name = args.family.replace(':', '_').replace('/', '_').lower()
    output_filename = f"benchmark_results/{safe_name}.json"
    
    last_sc = all_scorecards[-1]
    with open(output_filename, "w") as f:
        dump_data = {
            "model_manifest": manifest,
            "aggregate_metrics": metrics if args.runs > 1 else None,
            "runs_count": args.runs,
            "final_run_cases": {
                k: {
                    "schema_pass": v.schema_compliance_pass,
                    "invariant_pass": v.proposal_invariant_pass,
                    "grounding_pass": v.evidence_grounding_pass,
                    "eligibility_pass": v.eligibility_pass,
                    "quality_pass": v.investigation_quality_pass,
                    "is_ineligible_recall": v.is_ineligible_recall,
                    "is_inconclusive_recall": v.is_inconclusive_recall,
                    "is_false_certainty": v.is_false_certainty,
                    "is_adversarial_pass": v.is_adversarial_pass,
                    "latency": v.latency,
                    "validation_errors": v.validation_errors,
                    "reasoning_errors": v.reasoning_errors,
                    "raw_output": v.raw_output,
                    "status": v.status
                } for k, v in last_sc.cases.items()
            }
        }
        json.dump(dump_data, f, indent=2)
    print(f"\nDetailed scorecard saved to {output_filename}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run M4 benchmark against a local LLM.")
    
    # Manifest parameters
    parser.add_argument("--artifact", required=True, help="Exact model artifact name in the runtime (e.g., qwen2.5:7b-instruct-q4_K_M)")
    parser.add_argument("--family", required=True, help="Model family (e.g., Qwen3.5-9B, DeepSeek-R1-Distill-Qwen-7B, Phi-4-mini)")
    parser.add_argument("--quantization", required=True, help="Quantization level (e.g., 4-bit, Q4_K_M)")
    parser.add_argument("--runtime", default="Ollama", help="Runtime engine used (e.g., Ollama, MLX)")
    parser.add_argument("--runtime-version", default="latest", help="Version of the runtime engine")
    parser.add_argument("--hardware", default="M4 Air, 16 GB", help="Hardware the benchmark is running on")
    
    # API configuration
    parser.add_argument("--api-base", default="http://localhost:11434/v1", help="OpenAI-compatible API base URL")
    parser.add_argument("--api-key", default="ollama", help="API key")
    
    # Execution configuration
    parser.add_argument("--runs", type=int, default=3, help="Number of benchmark runs for stability")
    parser.add_argument("--seed", type=int, default=42, help="Starting random seed")
    
    args = parser.parse_args()
    run_benchmark(args)
