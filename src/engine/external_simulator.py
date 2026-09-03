import threading
from typing import Dict, Optional, Any

class SimulatedExternalSystem:
    """
    An in-memory simulator of external financial state (Merchant DB + Provider DB).
    Used to prove the FCE control boundary without requiring live credentials.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self.merchant_orders: Dict[str, Dict[str, Any]] = {}
        self.provider_payments: Dict[str, Dict[str, Any]] = {}
        self.fault_injections: Dict[str, str] = {} # e.g. target_id -> "TIMEOUT"

    def reset(self):
        with self._lock:
            self.merchant_orders.clear()
            self.provider_payments.clear()
            self.fault_injections.clear()

    def seed_merchant_order(self, order_id: str, amount: int, status: str = "UNPAID"):
        with self._lock:
            self.merchant_orders[order_id] = {
                "id": order_id,
                "amount": amount,
                "status": status
            }

    create_merchant_order = seed_merchant_order

    def seed_provider_payment(self, payment_id: str, order_id: str, amount: int, status: str = "CAPTURED"):
        with self._lock:
            self.provider_payments[payment_id] = {
                "id": payment_id,
                "order_id": order_id,
                "amount": amount,
                "status": status
            }

    create_provider_payment = seed_provider_payment

    def inject_fault(self, target_id: str, fault_type: str):
        """Allows injecting faults like 'TIMEOUT' for specific targets."""
        with self._lock:
            self.fault_injections[target_id] = fault_type

    def read_merchant_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self.merchant_orders.get(order_id)

    def read_provider_payment(self, payment_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self.provider_payments.get(payment_id)
            
    def read_provider_payment_by_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            for p in self.provider_payments.values():
                if p["order_id"] == order_id:
                    return p
            return None

    def update_merchant_order(self, order_id: str, new_status: str, expected_provider_state: Optional[str] = None) -> str:
        """Returns SUCCESS, TIMEOUT_UNKNOWN, or REJECTED. Implements atomic CAS against provider state."""
        with self._lock:
            fault = self.fault_injections.get(order_id)
            if fault == "TIMEOUT":
                return "TIMEOUT_UNKNOWN"
            if fault == "REJECT":
                return "REJECTED"

            if order_id not in self.merchant_orders:
                return "REJECTED" # Not found
                
            # Atomic CAS (Compare-And-Swap) precondition check
            if expected_provider_state:
                # Find the corresponding provider payment
                provider_payment = None
                for p in self.provider_payments.values():
                    if p["order_id"] == order_id:
                        provider_payment = p
                        break
                
                actual_provider_state = provider_payment["status"] if provider_payment else "UNKNOWN"
                matches = (
                    actual_provider_state == expected_provider_state
                    or (actual_provider_state in ("CAPTURED", "SETTLED") and expected_provider_state in ("CAPTURED", "SETTLED"))
                )
                if not matches:
                    return "REJECTED"  # Precondition failed, state drifted

            # Idempotency / State machine safety
            current = self.merchant_orders[order_id]["status"]
            if current == new_status:
                return "SUCCESS" # Already in desired state (idempotent)
            
            self.merchant_orders[order_id]["status"] = new_status
            return "SUCCESS"

    def refund_provider_payment(self, payment_id: str) -> str:
        with self._lock:
            fault = self.fault_injections.get(payment_id)
            if fault == "TIMEOUT":
                return "TIMEOUT_UNKNOWN"
            if fault == "REJECT":
                return "REJECTED"

            if payment_id not in self.provider_payments:
                return "REJECTED"

            current = self.provider_payments[payment_id]["status"]
            if current == "REFUNDED":
                return "SUCCESS" # idempotent
            if current != "CAPTURED":
                return "REJECTED"

            self.provider_payments[payment_id]["status"] = "REFUNDED"
            return "SUCCESS"

# Global singleton for the process, so tests/workers can share it
simulator = SimulatedExternalSystem()
