import pytest
pytestmark = [pytest.mark.legacy, pytest.mark.provider_mock]

import pytest
from src.integrations.razorpay.client import RazorpayClient

@pytest.mark.asyncio
async def test_create_and_get_order():
    client = RazorpayClient()
    try:
        # 1. Create Order
        order = await client.create_order(amount=10000, currency="INR", receipt="test_order")
        assert order.id.startswith("order_")
        assert order.amount == 10000
        assert order.status == "created"

        # 2. Get Order
        fetched_order = await client.get_order(order.id)
        assert fetched_order.id == order.id
        assert fetched_order.amount == 10000
    finally:
        await client.close()
