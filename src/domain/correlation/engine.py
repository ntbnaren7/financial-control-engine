from typing import List, Dict, Any
from datetime import timedelta

from src.domain.evidence.models import Evidence
from .models import CorrelationContext, CorrelationResult, CorrelationStatus

class DeterministicCorrelationEngine:
    def __init__(self, temporal_tolerance_days: int = 30):
        self.temporal_tolerance_days = temporal_tolerance_days

    def correlate_refund(self, internal_intents: List[Evidence], provider_records: List[Evidence]) -> List[CorrelationContext]:
        """
        Correlates internal intents with provider records.
        Returns a list of CorrelationContexts.
        """
        contexts: Dict[str, CorrelationContext] = {}
        
        # 1. Create contexts for each intent
        for intent in internal_intents:
            if intent.evidence_type != "REFUND_INTENT":
                continue
            contexts[intent.entity_id] = CorrelationContext(intent=intent)
            
        # 2. Evaluate provider records against intents
        for record in provider_records:
            if "RAZORPAY" not in record.evidence_type:
                continue
                
            # Extract receipt (the correlation key)
            receipt = None
            amount = None
            currency = None
            
            if record.source == "razorpay_webhook":
                entity = record.payload.get("payload", {}).get("refund", {}).get("entity", {})
                receipt = entity.get("receipt")
                amount = entity.get("amount") # in paise
                currency = entity.get("currency")
            elif record.source == "razorpay_api":
                receipt = record.payload.get("receipt")
                amount = record.payload.get("amount")
                currency = record.payload.get("currency")

            if not receipt:
                # If there's no receipt, we literally have no key to join on.
                # It's unmatched. We'll add it to an UNMATCHED context later, but for now we skip.
                continue

            # Does it match an intent?
            if receipt in contexts:
                intent = contexts[receipt].intent
                if not intent:
                    # Should not happen since we only match on receipts that exist in contexts,
                    # but satisfies type checking.
                    continue
                # Temporal check: Provider record should be AT OR AFTER the intent.
                # However, clock drift happens, so we allow a small negative buffer (e.g., 5 mins).
                # Also check maximum tolerance.
                time_diff = record.timestamp - intent.timestamp
                
                # Check bounds
                if time_diff < timedelta(minutes=-5):
                    # Provider record is inexplicably before the intent creation
                    status = CorrelationStatus.TEMPORAL_VIOLATION
                    temporal_check = False
                elif time_diff > timedelta(days=self.temporal_tolerance_days):
                    status = CorrelationStatus.TEMPORAL_VIOLATION
                    temporal_check = False
                else:
                    status = CorrelationStatus.CORRELATED
                    temporal_check = True

                # Scope Check (Is it the right merchant?)
                # In this simplified model, we assume all ingested records are for our merchant.
                # Real FCE would check merchant_id in the payload.
                entity_scope = True

                # Amount / Currency Check (for the correlation result, V1 actually classifies it)
                intent_amount = intent.payload.get("amount") if intent else None
                # Intent amount is typically in base units (e.g. Decimal), Razorpay is in paise.
                # We do a basic sanity check here.
                # Note: correlation doesn't fail if amount mismatches, we just record it.
                amount_check = False
                if intent_amount is not None and amount is not None:
                    # Very naive check: intent amount * 100 == razorpay amount
                    try:
                        if float(intent_amount) * 100 == float(amount):
                            amount_check = True
                    except (ValueError, TypeError):
                        pass

                intent_currency = intent.payload.get("currency") if intent else None
                currency_check = (intent_currency == currency) if intent_currency and currency else False
                
                result = CorrelationResult(
                    internal_evidence=intent,
                    provider_evidence=record,
                    status=status,
                    matched_by=f"receipt=={receipt}",
                    temporal_check=temporal_check,
                    entity_scope=entity_scope,
                    amount_check=amount_check,
                    currency_check=currency_check
                )
                
                contexts[receipt].results.append(result)
                contexts[receipt].provider_records.append(record)
            else:
                # We have a receipt, but no internal intent matches it.
                # This could be ORPHANED or AMBIGUOUS.
                # For now, we represent it as an unmatched record.
                # We don't have an intent context for it, so we might need a generic context.
                if "UNMATCHED" not in contexts:
                    contexts["UNMATCHED"] = CorrelationContext()
                
                contexts["UNMATCHED"].provider_records.append(record)
                contexts["UNMATCHED"].results.append(CorrelationResult(
                    internal_evidence=None,
                    provider_evidence=record,
                    status=CorrelationStatus.UNMATCHED,
                    matched_by=None
                ))

        return list(contexts.values())
