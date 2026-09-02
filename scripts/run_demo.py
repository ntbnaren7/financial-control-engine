import argparse
import json
import os
import sys
import uuid
import time
from decimal import Decimal

# Ensure absolute imports work when running from project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.domain.refunds.models import Refund
from src.recovery.uncertainty import resolve_refund_uncertainty, RetryPolicy
from tests.doubles.provider_double import ProviderDouble, E2EProviderAdapter
from src.domain.actions.models import Action, ActionType
from src.recovery.outbox import TransactionalOutbox, OutboxDispatcher

class Colors:
    def __init__(self, use_color: bool):
        self.BLUE = "\033[94m" if use_color else ""
        self.GREEN = "\033[92m" if use_color else ""
        self.YELLOW = "\033[93m" if use_color else ""
        self.RED = "\033[91m" if use_color else ""
        self.CYAN = "\033[96m" if use_color else ""
        self.MAGENTA = "\033[95m" if use_color else ""
        self.BOLD = "\033[1m" if use_color else ""
        self.RESET = "\033[0m" if use_color else ""

def generate_refund() -> Refund:
    return Refund(
        refund_intent_id=f"ref_{uuid.uuid4().hex[:8]}",
        provider_payment_id=f"pay_{uuid.uuid4().hex[:8]}",
        amount=Decimal('100.00'),
        currency="USD"
    )

def print_layer_header(title: str, colors: Colors):
    print(f"\n{colors.BOLD}{colors.CYAN}=== {title} ==={colors.RESET}\n")

def print_trace_structure(provider_text: str, fce_knowledge_text: str, control_text: str, colors: Colors):
    print(f"{colors.BOLD}WHAT ACTUALLY HAPPENED{colors.RESET}")
    print(f"{colors.YELLOW}PROVIDER:{colors.RESET} {provider_text}\n")
    
    print(f"{colors.BOLD}WHAT FCE CAN PROVE{colors.RESET}")
    print(f"{colors.BLUE}FCE KNOWLEDGE:{colors.RESET} {fce_knowledge_text}\n")
    
    print(f"{colors.BOLD}WHAT FCE IS ALLOWED TO DO{colors.RESET}")
    print(f"{colors.GREEN}CONTROL:{colors.RESET} {control_text}\n")
    print("-" * 60)

def run_layer_1(colors: Colors):
    print_layer_header("LAYER 1: BATCH EVALUATION ARTIFACT", colors)
    
    eval_file = os.path.join(os.path.dirname(__file__), "..", "artifacts", "v1_evaluation.json")
    if not os.path.exists(eval_file):
        print(f"{colors.RED}Error: {eval_file} not found.{colors.RESET}")
        print("Run `python scripts/run_batch_evaluation.py` first.")
        return

    with open(eval_file, 'r') as f:
        data = json.load(f)

    meta = data["run_metadata"]
    batch = data["batch_summary"]
    oracle = data["oracle_metrics"]
    safety = data["safety_metrics"]

    print(f"{colors.BOLD}{meta['records_processed']} records processed{colors.RESET}")
    print(f"{colors.BOLD}{batch['match_rate'] * 100:.1f}% initial match rate{colors.RESET}")
    print(f"{colors.BOLD}{batch['total_exceptions']} exceptions{colors.RESET}")
    print(f"{colors.BOLD}{batch['resolved_exceptions']} resolved{colors.RESET}")
    print(f"{colors.BOLD}{batch['unresolved_exceptions']} unresolved{colors.RESET}")
    print()
    print(f"{colors.BOLD}Oracle conformance: {oracle['oracle_conformant_records']}/{oracle['evaluable_records']} evaluable ({oracle['oracle_conformance_rate'] * 100:.0f}%){colors.RESET}")
    print(f"{colors.BOLD}{oracle['oracle_unavailable']}/{meta['records_processed']} oracle-unavailable{colors.RESET}")
    print()
    print(f"{colors.BOLD}{safety['safety_violations']} safety violations{colors.RESET}")
    print(f"{colors.BOLD}{safety['duplicate_financial_effects']} duplicate financial effects{colors.RESET}")
    print("-" * 60)

def run_layer_2(colors: Colors):
    print_layer_header("LAYER 2: LIVE DETERMINISTIC TRACES", colors)
    
    default_policy = RetryPolicy(max_attempts=3, provider_key_valid=True)
    
    # TRACE A
    print(f"{colors.BOLD}{colors.MAGENTA}Trace A — Executed but uncertain{colors.RESET}\n")
    double_a = ProviderDouble()
    adapter_a = E2EProviderAdapter(double_a)
    refund_a = generate_refund()
    key_a = refund_a.get_provider_idempotency_key()
    
    # Model: dispatched -> response lost -> but provider ACTUALLY executed it
    # Easiest way to simulate without full runner is to manually add it to double's history
    # which will then be found by query
    action_a = Action(action_type=ActionType.CONTROLLED_REFUND, incident_id=refund_a.refund_intent_id, idempotency_key=key_a)
    adapter_a.dispatch_action(action_a)
    adapter_a.observations.clear() # FCE lost the response
    
    outcome_a, _ = resolve_refund_uncertainty(refund_a, [], adapter_a, default_policy)
    
    exec_str_a = outcome_a.reconstructed_state.execution.value if outcome_a.reconstructed_state.execution else "None"
    
    print_trace_structure(
        "refund dispatched → response lost (simulated)",
        f"UNKNOWN → provider query → AUTHORITATIVE_EXECUTED → {outcome_a.reconstructed_state.knowledge_state.value} / {exec_str_a}",
        outcome_a.status.value,
        colors
    )
    
    # TRACE B
    print(f"{colors.BOLD}{colors.MAGENTA}Trace B — Safe recovery{colors.RESET}\n")
    double_b = ProviderDouble()
    adapter_b = E2EProviderAdapter(double_b)
    outbox_b = TransactionalOutbox()
    dispatcher_b = OutboxDispatcher(outbox_b, adapter_b)
    
    refund_b = generate_refund()
    key_b = refund_b.get_provider_idempotency_key()
    
    # Model: dispatched -> ambiguous -> provider did NOT execute it
    double_b.configure_ambiguous(key_b)
    action_b = Action(action_type=ActionType.CONTROLLED_REFUND, incident_id=refund_b.refund_intent_id, idempotency_key=key_b)
    outbox_b.publish_action(action_b)
    dispatcher_b.process_pending()
    adapter_b.observations.clear() # Ensure clean state for query
    
    outcome_b, _ = resolve_refund_uncertainty(refund_b, [], adapter_b, default_policy)
    
    # Authorize retry and commit to outbox
    if outcome_b.status.value == "AUTHORIZED_RETRY":
        retry_action = Action(
            action_type=ActionType.CONTROLLED_REFUND,
            incident_id=refund_b.refund_intent_id,
            idempotency_key=key_b
        )
        double_b._force_ambiguous_keys.remove(key_b) # Recovery attempt should succeed
        outbox_b.publish_action(retry_action)
        dispatcher_b.process_pending()
        
    effects_b = double_b.get_financial_effect_count(refund_b.refund_intent_id)
    
    exec_str_b = outcome_b.reconstructed_state.execution.value if outcome_b.reconstructed_state.execution else "None"
    
    print_trace_structure(
        "refund dispatched → ambiguous → actual effect NOT_EXECUTED",
        f"UNKNOWN → authoritative NOT_EXECUTED → {outcome_b.reconstructed_state.knowledge_state.value} / {exec_str_b}",
        f"{outcome_b.status.value} → same intent [{refund_b.refund_intent_id}] / key [{key_b[:8]}...] → outbox → provider → {effects_b} financial effect",
        colors
    )

    # TRACE C
    print(f"{colors.BOLD}{colors.MAGENTA}Trace C — Insufficient evidence{colors.RESET}\n")
    double_c = ProviderDouble()
    adapter_c = E2EProviderAdapter(double_c)
    
    refund_c = generate_refund()
    key_c = refund_c.get_provider_idempotency_key()
    
    # Model: ambiguous -> non-authoritative/failed query
    double_c.configure_query_failure(key_c)
    
    outcome_c, _ = resolve_refund_uncertainty(refund_c, [], adapter_c, default_policy)
    
    print_trace_structure(
        "refund dispatched → ambiguous → network partition / provider API 500",
        f"UNKNOWN → non-authoritative / failed query → {outcome_c.reconstructed_state.knowledge_state.value}",
        f"{outcome_c.status.value}\n{colors.RED}{colors.BOLD}No financial action authorized.{colors.RESET}",
        colors
    )

def main():
    parser = argparse.ArgumentParser(description="V1 Financial Control Engine Demo")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI terminal colors")
    args = parser.parse_args()

    colors = Colors(use_color=not args.no_color)
    
    run_layer_1(colors)
    time.sleep(1) # Slight dramatic pause between layers
    run_layer_2(colors)

if __name__ == "__main__":
    main()
