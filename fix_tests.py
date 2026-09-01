with open("tests/integration/test_failure_paths.py", "r") as f:
    content = f.read()

content = content.replace("@pytest.fixture(autouse=True)\nasync def setup_teardown_db():\n    async with engine.begin() as conn:\n        await conn.run_sync(EvidenceBase.metadata.create_all)\n        await conn.run_sync(MerchantBase.metadata.create_all)\n    yield\n    async with engine.begin() as conn:\n        await conn.run_sync(EvidenceBase.metadata.drop_all)\n        await conn.run_sync(MerchantBase.metadata.drop_all)", "async def setup_db():\n    async with engine.begin() as conn:\n        await conn.run_sync(EvidenceBase.metadata.drop_all)\n        await conn.run_sync(EvidenceBase.metadata.create_all)\n        await conn.run_sync(MerchantBase.metadata.create_all)\n\nasync def teardown_db():\n    async with engine.begin() as conn:\n        await conn.run_sync(EvidenceBase.metadata.drop_all)\n        await conn.run_sync(MerchantBase.metadata.drop_all)")

# For each test function, add await setup_db() and try/finally
import re

def replacer(match):
    func_sig = match.group(1)
    func_body = match.group(2)
    # indent the body
    indented_body = "\n".join("    " + line if line.strip() else line for line in func_body.split("\n"))
    return f"{func_sig}\n    await setup_db()\n    try:\n{indented_body}\n    finally:\n        await teardown_db()"

content = re.sub(r'(@pytest\.mark\.asyncio\nasync def test_[^\(]+\(\):)\n(.*?)(?=\n@pytest\.mark\.asyncio|\Z)', replacer, content, flags=re.DOTALL)

with open("tests/integration/test_failure_paths.py", "w") as f:
    f.write(content)
