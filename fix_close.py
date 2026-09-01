with open("tests/integration/test_adversarial_control.py", "r") as f:
    content = f.read()

replacement = """class MockAsyncClient:
    def __init__(self, content, side_effect=None):
        self.content = content
        self.side_effect = side_effect
    
    async def create(self, **kwargs):
        if self.side_effect:
            await self.side_effect()
        return MockAsyncChatCompletion(self.content)
        
    async def close(self):
        pass"""

content = content.replace("""class MockAsyncClient:
    def __init__(self, content, side_effect=None):
        self.content = content
        self.side_effect = side_effect
    
    async def create(self, **kwargs):
        if self.side_effect:
            await self.side_effect()
        return MockAsyncChatCompletion(self.content)""", replacement)

with open("tests/integration/test_adversarial_control.py", "w") as f:
    f.write(content)
