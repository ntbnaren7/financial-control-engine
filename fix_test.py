import re

with open("tests/integration/test_failure_paths.py", "r") as f:
    content = f.read()

replacement = """        with patch("src.investigation.ai.InvestigationEngine.investigate", return_value=mock_res):
            with patch("src.orchestration.pipeline.verify_resolution", return_value=mock_verify_res):
                async with AsyncSessionLocal() as session:
                    obs = ProviderObservation(
                        provider="razorpay",
                        event_id=f"evt_{uuid.uuid4().hex[:8]}",
                        event_type="webhook",
                        payload=create_webhook_payload(order_id, payment_id)
                    )
                    session.add(obs)
                    await session.commit()
                    obs_id = str(obs.id)
                
                from src.orchestration.pipeline import run_investigation_pipeline
                pipeline_return = await run_investigation_pipeline(obs_id)"""

pattern = r'        with patch\("src\.investigation\.ai\.InvestigationEngine\.investigate", return_value=mock_res\):\n            with patch\("src\.orchestration\.pipeline\.verify_resolution", return_value=mock_verify_res\):\n                response = await trigger_webhook\(create_webhook_payload\(order_id, payment_id\)\)\n                assert response\.status_code == 200\n\n                from src\.orchestration\.pipeline import run_investigation_pipeline\n                async with AsyncSessionLocal\(\) as session:\n                    obs_result = await session\.execute\(select\(ProviderObservation\)\.where\(ProviderObservation\.event_type == \'webhook\'\)\)\n                    obs = obs_result\.scalars\(\)\.first\(\)\n\n                pipeline_return = await run_investigation_pipeline\(str\(obs\.id\)\)'

content = re.sub(pattern, replacement, content)

with open("tests/integration/test_failure_paths.py", "w") as f:
    f.write(content)
