import os
import re

def fix_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()
    
    # We want to replace ANY instance of setting get_payment_refunds to also set get_payment
    # mock_razorpay_client.get_payment_refunds = AsyncMock(...)
    # Let's just find "mock_razorpay_client = MagicMock()"
    # and replace it with a helper function call that creates a valid mock.
    
    setup_code = '''
def _create_mock_client():
    from unittest.mock import MagicMock, AsyncMock
    client = MagicMock()
    mock_payment = MagicMock()
    mock_payment.model_dump.return_value = {"id": "pay_test", "status": "captured", "amount": 1000, "currency": "INR", "created_at": 1600000000}
    client.get_payment = AsyncMock(return_value=mock_payment)
    mock_refund = MagicMock()
    mock_refund.model_dump.return_value = {"id": "rfnd_test", "status": "processed", "amount": 1000, "currency": "INR", "created_at": 1600000000}
    client.get_payment_refunds = AsyncMock(return_value=[mock_refund])
    return client
mock_razorpay_client = _create_mock_client()
'''

    new_content = re.sub(r'mock_razorpay_client\s*=\s*MagicMock\(\)', setup_code.strip(), content)
    # also remove any explicit get_payment_refunds overrides so our default holds
    new_content = re.sub(r'mock_razorpay_client\.get_payment_refunds\s*=\s*AsyncMock\(.*?\)\n', '', new_content)

    if content != new_content:
        with open(filepath, 'w') as f:
            f.write(new_content)
            print(f"Fixed {filepath}")

for root, dirs, files in os.walk('tests'):
    for file in files:
        if file.endswith('.py'):
            fix_file(os.path.join(root, file))
