import re

with open("tests/integration/test_adversarial_control.py", "r") as f:
    content = f.read()

# Replace:
# with patch("src.investigation.ai.InvestigationEngine.client") as mock_engine_client:
#     mock_engine_client.chat.completions = mock_client
# with:
# with patch("src.investigation.ai.AsyncOpenAI", return_value=mock_client):

content = re.sub(
    r'with patch\("src\.investigation\.ai\.InvestigationEngine\.client"\) as mock_engine_client:\n\s*mock_engine_client\.chat\.completions = mock_client',
    r'mock_client.chat = MagicMock(completions=mock_client)\n        with patch("src.investigation.ai.AsyncOpenAI", return_value=mock_client):',
    content
)

with open("tests/integration/test_adversarial_control.py", "w") as f:
    f.write(content)
