import asyncio
from integrations.razorpay.client import RazorpayClient
import sys

async def main():
    client = RazorpayClient()
    try:
        if len(sys.argv) > 1:
            # We have a payment ID argument to test retrieval
            payment_id = sys.argv[1]
            print(f"Retrieving payment: {payment_id}...")
            payment = await client.get_payment(payment_id)
            print(f"Payment retrieved successfully!")
            print(f"ID: {payment.id}")
            print(f"Order ID: {payment.order_id}")
            print(f"Amount: {payment.amount} {payment.currency}")
            print(f"Status: {payment.status}")
            print(f"Captured: {payment.captured}")
        else:
            # Create an order
            print("Creating test order...")
            order = await client.create_order(amount=50000, currency="INR", receipt="test_receipt_001")
            print(f"Order created successfully: {order.id}")
            print(f"Status: {order.status}")
            print("\n--- Next Steps ---")
            print(f"1. Go to your Razorpay Dashboard (Test Mode).")
            print(f"2. Manually complete a test checkout for this order ID or create a Payment Link.")
            print("3. Retrieve the resulting `pay_...` ID.")
            print("4. Run this script again with the payment ID as an argument:")
            print(f"   PYTHONPATH=src uv run python scripts/test_integration.py pay_xxxxxxxxx")
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
