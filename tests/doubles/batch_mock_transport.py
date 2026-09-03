"""
Phase F — Batch Mock Transport

Routes Razorpay API responses per investigation sub-case (C1–C5).
Uses the payment_id embedded in the request URL to select the correct
programmed response.

This transport is the ONLY component that knows about the investigation
sub-case labels.  Everything else in the batch runner reads only the
V1 output.

Sub-case behaviour:
  C1_MISSING_WEBHOOK   — Refund found (correct amount).      → V1: MATCH
  C2_PROVIDER_DROPPED  — Refund not found.                   → V1: ABSENT_EXECUTION
  C3_AMOUNT_MISMATCH   — Refund found (wrong amount).        → V1: VALUE_MISMATCH
  C4_PROVIDER_OUTAGE   — HTTP 503 Service Unavailable.       → V1: EPISTEMIC_STALEMATE
  C5_BOUNDARY_REJECT   — Never called (D4 rejects the LLM). → V1: EPISTEMIC_STALEMATE

The transport is initialised with a mapping of
  payment_id → (sub_case, expected_amount)
so it can return a deterministic, case-appropriate response without any
shared mutable state.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, Optional

import httpx


class BatchMockTransport(httpx.AsyncBaseTransport):
    """
    Batch-evaluation mock for Razorpay.

    payment_routes maps provider_payment_id → dict with keys:
      sub_case        (str)   e.g. "C1_MISSING_WEBHOOK"
      expected_amount (int)   the amount the expectation was for
    """

    def __init__(self, payment_routes: Dict[str, Dict[str, Any]]) -> None:
        self._routes = payment_routes
        self.query_calls: list[str] = []   # payment_ids queried

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url = request.url.path

        # Only the query endpoint is relevant for Phase F investigation
        if request.method == "GET" and url.endswith("refunds"):
            payment_id = url.split("/")[3]  # /v1/payments/{id}/refunds
            self.query_calls.append(payment_id)
            return await self._respond_for(payment_id, request)

        # POST to create refund — not used in Phase F (investigation only)
        return httpx.Response(404, text="Not implemented in BatchMockTransport", request=request)

    async def _respond_for(self, payment_id: str, request: httpx.Request) -> httpx.Response:
        route = self._routes.get(payment_id)

        if route is None:
            # Unknown payment — return empty list (treated as not found by verifier)
            return self._collection([], request)

        sub_case: str = route["sub_case"]
        amount: int = route["expected_amount"]

        if sub_case == "C1_MISSING_WEBHOOK":
            # Refund was processed; webhook was lost.  Return a successful refund.
            # receipt must match case.expectation.intent_id for the verifier's filter.
            receipt = route.get("intent_id", "")
            return self._collection(
                [self._refund_item(payment_id, amount, "processed", receipt=receipt)],
                request,
            )

        elif sub_case == "C2_PROVIDER_DROPPED":
            # Provider dropped the refund.  Nothing found.
            return self._collection([], request)

        elif sub_case == "C3_AMOUNT_MISMATCH":
            # Provider refunded a different amount — intentional discrepancy.
            # receipt must match so the verifier doesn't discard the item.
            wrong_amount = amount - 100  # Always less than expected
            receipt = route.get("intent_id", "")
            return self._collection(
                [self._refund_item(payment_id, wrong_amount, "processed", receipt=receipt)],
                request,
            )

        elif sub_case == "C4_PROVIDER_OUTAGE":
            # Simulates a provider-side 503 during verification.
            # raise_for_status() in the client will raise HTTPStatusError,
            # which the verifier's httpx.HTTPError handler will catch.
            return httpx.Response(503, text="Service Unavailable", request=request)

        elif sub_case == "C5_BOUNDARY_REJECT":
            # D4 rejects the hypothesis before D5 is called — this endpoint
            # should never be reached for C5.  If it is, that is a bug.
            raise AssertionError(
                f"BatchMockTransport: D5 was called for {sub_case}. "
                "D4 should have rejected the hypothesis before reaching the verifier."
            )

        else:
            return self._collection([], request)

    def _refund_item(self, payment_id: str, amount: int, status: str, receipt: str = "") -> dict:
        return {
            "id": f"rfnd_{uuid.uuid4().hex[:14]}",
            "entity": "refund",
            "amount": amount,
            "currency": "INR",
            "payment_id": payment_id,
            "status": status,
            "receipt": receipt,  # Must match case.expectation.intent_id for verifier filter
            "created_at": int(time.time()),
            "speed_processed": "normal",
        }

    @staticmethod
    def _collection(items: list, request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"entity": "collection", "count": len(items), "items": items},
            request=request,
        )
