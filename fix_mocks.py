import os
import glob

def fix_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()
    
    if 'mock_razorpay_client = MagicMock()' in content:
        # replace with proper setup
        setup = '''mock_razorpay_client = MagicMock()
    
    mock_payment = MagicMock()
    mock_payment.model_dump.return_value = {"id": "pay_test", "status": "captured", "amount": 1000, "currency": "INR", "created_at": 1600000000}
    mock_razorpay_client.get_payment = AsyncMock(return_value=mock_payment)'''
        content = content.replace('mock_razorpay_client = MagicMock()', setup)
        
        with open(filepath, 'w') as f:
            f.write(content)
            print(f"Fixed {filepath}")

for root, dirs, files in os.walk('tests'):
    for file in files:
        if file.endswith('.py'):
            fix_file(os.path.join(root, file))
