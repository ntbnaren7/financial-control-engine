"""
Unit tests for the Independent Provider Double.

These tests verify that the provider double itself correctly tracks financial
effects, enforces idempotency, handles scenario overrides, and exposes a
reliable oracle. If these pass, the double can be trusted as the ground-truth
oracle in the adversarial matrix (A1-P2).
"""
import pytest
from datetime import timedelta
from decimal import Decimal

from tests.doubles.provider_double import (
    ProviderDouble,
    ProviderTransportResult,
    ProviderQueryResult,
)


def make_payload(amount: Decimal = Decimal("500.00"), currency: str = "INR") -> dict:
    return {"amount": str(amount), "currency": currency, "payment_id": "pay_001"}


# ── Effect-count oracle ────────────────────────────────────────────────────────

class TestOracleBasics:
    def test_new_intent_has_zero_effects(self):
        double = ProviderDouble()
        assert double.get_financial_effect_count("ri_001") == 0

    def test_successful_dispatch_records_one_effect(self):
        double = ProviderDouble()
        result = double.dispatch_refund("ri_001", "key_001", make_payload())
        assert result == ProviderTransportResult.ACCEPTED_EXECUTED
        assert double.get_financial_effect_count("ri_001") == 1

    def test_idempotent_replay_does_not_double_count(self):
        double = ProviderDouble()
        double.dispatch_refund("ri_001", "key_001", make_payload())
        double.dispatch_refund("ri_001", "key_001", make_payload())  # same key + payload
        assert double.get_financial_effect_count("ri_001") == 1

    def test_assert_at_most_one_effect_passes_on_zero(self):
        double = ProviderDouble()
        double.assert_at_most_one_effect("ri_001")  # should not raise

    def test_assert_at_most_one_effect_passes_on_one(self):
        double = ProviderDouble()
        double.dispatch_refund("ri_001", "key_001", make_payload())
        double.assert_at_most_one_effect("ri_001")  # should not raise

    def test_assert_at_most_one_effect_raises_on_two(self):
        """
        If the implementation has a bug that causes two effects, the oracle must
        surface it. This test directly injects two effects to verify the assertion
        mechanism works.
        """
        double = ProviderDouble()
        # Manually inject a second effect (simulates a buggy implementation path)
        double.dispatch_refund("ri_001", "key_001", make_payload())
        double._record_effect("ri_001", "key_002", double._clock)  # bypass idempotency
        assert double.get_financial_effect_count("ri_001") == 2
        with pytest.raises(AssertionError, match="2 financial effects"):
            double.assert_at_most_one_effect("ri_001")


# ── Mutation outcome semantics ────────────────────────────────────────────────

class TestMutationOutcomes:
    def test_ambiguous_timeout_returns_ambiguous(self):
        double = ProviderDouble()
        double.configure_ambiguous("key_timeout")
        result = double.dispatch_refund("ri_001", "key_timeout", make_payload())
        assert result == ProviderTransportResult.AMBIGUOUS_OUTCOME
        # No financial effect because the provider dropped before executing
        assert double.get_financial_effect_count("ri_001") == 0

    def test_drop_response_executes_but_appears_ambiguous(self):
        """Scenario A2 / O3: Provider executes, FCE sees ambiguity (dropped response)."""
        double = ProviderDouble()
        double.configure_drop("key_drop")
        result = double.dispatch_refund("ri_001", "key_drop", make_payload())
        assert result == ProviderTransportResult.AMBIGUOUS_OUTCOME
        # Provider DID execute — this is the key A2 / O3 invariant
        assert double.get_financial_effect_count("ri_001") == 1

    def test_explicit_rejection_produces_no_effect(self):
        """Scenario B: 400 terminal rejection."""
        double = ProviderDouble()
        double.configure_reject("key_reject")
        result = double.dispatch_refund("ri_001", "key_reject", make_payload())
        assert result == ProviderTransportResult.EXPLICITLY_REJECTED
        assert double.get_financial_effect_count("ri_001") == 0

    def test_pending_queues_webhook_without_immediate_effect(self):
        """Scenario D: 200 PENDING."""
        double = ProviderDouble()
        double.configure_pending("key_pending")
        result = double.dispatch_refund("ri_001", "key_pending", make_payload())
        assert result == ProviderTransportResult.ACCEPTED_PENDING
        # No synchronous effect; effect comes via webhook (provider processes async)
        assert double.get_financial_effect_count("ri_001") == 0
        webhooks = double.deliver_webhooks("ri_001")
        assert len(webhooks) == 1

    def test_idempotency_mismatch_is_detected(self):
        """Scenario E / N: Same key, different payload."""
        double = ProviderDouble()
        payload_a = make_payload(Decimal("500"))
        payload_b = make_payload(Decimal("999"))  # different amount
        double.dispatch_refund("ri_001", "key_001", payload_a)
        result = double.dispatch_refund("ri_001", "key_001", payload_b)
        assert result == ProviderTransportResult.IDEMPOTENCY_MISMATCH
        # Effect count unchanged — second attempt rejected
        assert double.get_financial_effect_count("ri_001") == 1


# ── Query authority semantics ─────────────────────────────────────────────────

class TestQueryAuthority:
    def test_authoritative_query_after_execution(self):
        double = ProviderDouble()
        double.dispatch_refund("ri_001", "key_001", make_payload())
        result = double.query_refund_status("key_001")
        assert result == ProviderQueryResult.AUTHORITATIVE_EXECUTED

    def test_authoritative_not_executed_when_key_never_seen(self):
        double = ProviderDouble()
        result = double.query_refund_status("key_never_sent")
        assert result == ProviderQueryResult.AUTHORITATIVE_NOT_EXECUTED

    def test_authoritative_not_executed_after_rejection(self):
        """A rejected request leaves no effect — query should confirm NOT_EXECUTED."""
        double = ProviderDouble()
        double.configure_reject("key_rej")
        double.dispatch_refund("ri_001", "key_rej", make_payload())
        result = double.query_refund_status("key_rej")
        assert result == ProviderQueryResult.AUTHORITATIVE_NOT_EXECUTED

    def test_stale_replica_returns_non_authoritative(self):
        """Scenario F / M: Replica-lagged query must NOT become AUTHORITATIVE_NOT_EXECUTED."""
        double = ProviderDouble()
        double.dispatch_refund("ri_001", "key_001", make_payload())
        double.configure_stale_query("key_001")
        result = double.query_refund_status("key_001")
        assert result == ProviderQueryResult.NON_AUTHORITATIVE_QUERY

    def test_query_failure_returns_query_failed(self):
        double = ProviderDouble()
        double.configure_query_failure("key_001")
        result = double.query_refund_status("key_001")
        assert result == ProviderQueryResult.QUERY_FAILED

    def test_global_replica_lag_returns_non_authoritative(self):
        double = ProviderDouble()
        double.replica_lag_enabled = True
        double.dispatch_refund("ri_001", "key_001", make_payload())
        result = double.query_refund_status("key_001")
        assert result == ProviderQueryResult.NON_AUTHORITATIVE_QUERY


# ── Idempotency expiry ─────────────────────────────────────────────────────────

class TestIdempotencyExpiry:
    def test_key_within_retention_is_safe(self):
        """Scenario P (before expiry): same key replay is idempotent."""
        double = ProviderDouble()
        double.idempotency_retention = timedelta(hours=24)
        double.dispatch_refund("ri_001", "key_001", make_payload())
        # Second dispatch immediately → still within window
        result = double.dispatch_refund("ri_001", "key_001", make_payload())
        assert result == ProviderTransportResult.ACCEPTED_EXECUTED
        assert double.get_financial_effect_count("ri_001") == 1

    def test_expired_key_allows_fresh_dispatch(self):
        """Scenario P (after expiry): provider no longer recognises the old key."""
        double = ProviderDouble()
        double.idempotency_retention = timedelta(hours=24)
        double.dispatch_refund("ri_001", "key_001", make_payload())
        # Simulate expiry
        double.expire_idempotency_for("key_001")
        # Re-dispatch with the same key — provider treats it as fresh
        result = double.dispatch_refund("ri_001", "key_001", make_payload())
        # Provider executes again (no longer idempotent after expiry)
        assert result == ProviderTransportResult.ACCEPTED_EXECUTED
        # This will show 2 effects — proving FCE MUST verify before retrying after expiry
        assert double.get_financial_effect_count("ri_001") == 2


# ── Webhook delivery ──────────────────────────────────────────────────────────

class TestWebhookDelivery:
    def test_successful_dispatch_queues_webhook(self):
        double = ProviderDouble()
        double.dispatch_refund("ri_001", "key_001", make_payload())
        webhooks = double.get_emitted_webhooks("ri_001")
        assert len(webhooks) == 1

    def test_deliver_webhooks_marks_delivered(self):
        double = ProviderDouble()
        double.dispatch_refund("ri_001", "key_001", make_payload())
        delivered = double.deliver_webhooks("ri_001")
        assert len(delivered) == 1
        # Second call returns nothing — already delivered
        delivered2 = double.deliver_webhooks("ri_001")
        assert len(delivered2) == 0

    def test_late_webhook_at_offset(self):
        """Scenario G: webhook arrives with a time delay."""
        double = ProviderDouble()
        double.dispatch_refund("ri_001", "key_001", make_payload())
        delivered = double.deliver_webhook_at_offset("ri_001", offset_seconds=30)
        assert len(delivered) == 1

    def test_no_webhook_for_ambiguous_timeout(self):
        """Scenario A1: provider drops before executing, so no webhook is queued."""
        double = ProviderDouble()
        double.configure_ambiguous("key_timeout")
        double.dispatch_refund("ri_001", "key_timeout", make_payload())
        webhooks = double.get_emitted_webhooks("ri_001")
        assert len(webhooks) == 0


# ── Scope isolation ───────────────────────────────────────────────────────────

class TestScopeIsolation:
    def test_two_intents_on_same_payment_are_independent(self):
        """Scenario L: Two distinct refund intents on the same payment."""
        double = ProviderDouble()
        payload_r1 = {"amount": "500", "currency": "INR", "payment_id": "pay_001"}
        payload_r2 = {"amount": "300", "currency": "INR", "payment_id": "pay_001"}

        double.dispatch_refund("ri_001", "key_r1", payload_r1)
        double.dispatch_refund("ri_002", "key_r2", payload_r2)

        assert double.get_financial_effect_count("ri_001") == 1
        assert double.get_financial_effect_count("ri_002") == 1

        # Oracle per-intent, not aggregated
        double.assert_at_most_one_effect("ri_001")
        double.assert_at_most_one_effect("ri_002")

    def test_r1_execution_does_not_affect_r2_oracle(self):
        double = ProviderDouble()
        double.dispatch_refund("ri_001", "key_r1", make_payload())
        # R2 was never dispatched
        assert double.get_financial_effect_count("ri_002") == 0
