import httpx
import json
import uuid
import time
from typing import Dict, Any, List

class RazorpayMockTransport(httpx.AsyncBaseTransport):
    """
    Hermetic in-memory simulator for Razorpay API.
    Simulates /v1/payments/{id}/refund and /v1/payments/{id}/refunds endpoints.
    """
    def __init__(self):
        self.refunds: List[Dict[str, Any]] = []
        
        # Test hooks
        self.simulate_timeout_on_create = False
        self.simulate_504_on_create = False
        self.simulate_500_on_query = False
        self.simulate_timeout_on_query = False
        self.record_create_calls = []
        self.record_query_calls = []
        
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url = request.url.path
        
        if request.method == "POST" and "/refund" in url and not url.endswith("refunds"):
            self.record_create_calls.append(request)
            
            if self.simulate_timeout_on_create:
                # We record the refund locally but raise timeout to simulate connection drop post-processing
                self._create_refund(request)
                raise httpx.TimeoutException("Mock transport timeout")
                
            if self.simulate_504_on_create:
                return httpx.Response(504, request=request)
                
            resp_data = self._create_refund(request)
            return httpx.Response(200, json=resp_data, request=request)
            
        elif request.method == "GET" and url.endswith("refunds"):
            self.record_query_calls.append(request)
            
            if self.simulate_timeout_on_query:
                raise httpx.TimeoutException("Mock transport timeout")
            if self.simulate_500_on_query:
                return httpx.Response(500, request=request)
                
            payment_id = url.split("/")[2]
            payment_refunds = [r for r in self.refunds if r["payment_id"] == payment_id]
            
            resp_data = {
                "entity": "collection",
                "count": len(payment_refunds),
                "items": payment_refunds
            }
            return httpx.Response(200, json=resp_data, request=request)
            
        return httpx.Response(404, text="Not Found", request=request)
        
    def _create_refund(self, request: httpx.Request) -> dict:
        body = json.loads(request.content)
        payment_id = request.url.path.split("/")[2]
        
        new_refund = {
            "id": f"rfnd_{uuid.uuid4().hex[:14]}",
            "entity": "refund",
            "amount": body.get("amount"),
            "currency": "INR",
            "payment_id": payment_id,
            "status": "processed",
            "receipt": body.get("receipt"),
            "notes": body.get("notes"),
            "created_at": int(time.time()),
            "batch_id": None,
            "speed_processed": "normal",
            "speed_requested": "normal"
        }
        self.refunds.append(new_refund)
        return new_refund
