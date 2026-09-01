import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.evidence.db import AsyncSessionLocal as session_maker
from src.evidence.gatherer import DatabaseEvidenceGatherer
from src.investigation.config import LLMConfig
from src.investigation.ai import InvestigationEngine
from scripts.validate_scenarios import SCENARIOS, run_scenario

MODELS_TO_TEST = [
    "phi4-mini:3.8b-q4_K_M",
    "deepseek-r1:7b",
    "qwen3.5:9b",
    "gemma3:4b"
]

TARGET_SCENARIOS = ["SC-03", "SC-06"]

async def evaluate_model(model_name: str, gatherer: DatabaseEvidenceGatherer, target_scenarios: list) -> list:
    print(f"\n========================================================")
    print(f"Evaluating Model: {model_name}")
    print(f"========================================================")
    
    config = LLMConfig(
        model_name=model_name,
        base_url=os.environ.get("OLLAMA_HOST", "http://localhost:11434/v1"),
        api_key="ollama",
        temperature=0.0
    )
    engine = InvestigationEngine(config)
    results = []
    
    for sc in target_scenarios:
        print(f"  ▶ Running [{sc.scenario_id}] {sc.name}... ", end="", flush=True)
        start_time = time.time()
        
        try:
            res = await run_scenario(sc, engine, gatherer)
            latency = time.time() - start_time
            print(f"Done ({latency:.2f}s)")
            
            # Categorize the status
            status_val = res["status"]
            if status_val in ["ACCEPTED", "PROPOSAL_SEMANTIC_CONFLICT"]:
                structural_status = "PASS"
            else:
                structural_status = status_val
                
            if status_val == "ACCEPTED":
                semantic_status = "PASS"
            elif status_val == "PROPOSAL_SEMANTIC_CONFLICT":
                semantic_status = "FAIL"
            else:
                semantic_status = "N/A"
            
            results.append({
                "model": model_name,
                "scenario": sc.scenario_id,
                "top_hypothesis": res["model_top_hypothesis"],
                "rationale": res["rationale"],
                "structural_status": structural_status,
                "semantic_status": semantic_status,
                "latency": latency
            })
        except Exception as e:
            latency = time.time() - start_time
            print(f"ERROR ({latency:.2f}s) - {str(e)}")
            results.append({
                "model": model_name,
                "scenario": sc.scenario_id,
                "top_hypothesis": "ERROR",
                "rationale": str(e),
                "structural_status": "ERROR",
                "semantic_status": "ERROR",
                "latency": latency
            })
            
    await engine.client.close()
    return results

async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Model-Agnostic Evaluation Harness")
    parser.add_argument("--models", type=str, default=",".join(MODELS_TO_TEST), help="Comma-separated list of models to evaluate")
    parser.add_argument("--scenarios", type=str, default=",".join(TARGET_SCENARIOS), help="Comma-separated list of scenarios to run")
    args = parser.parse_args()

    models = [m.strip() for m in args.models.split(",")]
    target_ids = [s.strip() for s in args.scenarios.split(",")]
    
    scenarios = [sc for sc in SCENARIOS if sc.scenario_id in target_ids]
    
    print("=" * 80)
    print("FINANCIAL CONTROL ENGINE — CROSS-MODEL EVALUATION HARNESS")
    print(f"Models: {', '.join(models)}")
    print(f"Scenarios: {', '.join(target_ids)}")
    print("=" * 80)

    gatherer = DatabaseEvidenceGatherer(session_maker)
    all_results = []
    
    for model in models:
        res = await evaluate_model(model, gatherer, scenarios)
        all_results.extend(res)
        
    print("\n" + "=" * 160)
    print(f"{'Model':<25} | {'Scenario':<9} | {'Latency':<8} | {'Structural':<12} | {'Semantic':<10} | {'Top Hypothesis':<35} | {'Rationale'}")
    print("-" * 160)
    for r in all_results:
        model_name = r["model"]
        if len(model_name) > 24:
            model_name = model_name[:21] + "..."
            
        rationale = r['rationale'] or "N/A"
        if len(rationale) > 50:
            rationale = rationale[:47] + "..."
            
        print(f"{model_name:<25} | {r['scenario']:<9} | {r['latency']:<7.2f}s | {r['structural_status']:<12} | {r['semantic_status']:<10} | {str(r['top_hypothesis']):<35} | {rationale}")
    print("=" * 160)
    
if __name__ == "__main__":
    asyncio.run(main())
