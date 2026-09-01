import re

with open("tests/integration/test_failure_paths.py", "r") as f:
    content = f.read()

def replacer(match):
    return """@pytest.mark.asyncio
async def test_post_action_verification_fails():
    await setup_db()
    try:
        order_id = f"order_{uuid.uuid4().hex[:8]}"
        payment_id = f"pay_{uuid.uuid4().hex[:8]}"
        await seed_db(order_id, payment_id)

        from src.recovery.verifier import VerificationResult, VerificationStatus
        mock_verify_res = VerificationResult(status=VerificationStatus.VERIFICATION_FAILED, message="Still UNPAID")

        mock_res = create_mock_m4_result(V0HypothesisType.WEBHOOK_PROCESSED_STATE_NOT_UPDATED)

        with patch("src.investigation.ai.InvestigationEngine.investigate", return_value=mock_res):
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
                pipeline_return = await run_investigation_pipeline(obs_id)

                assert isinstance(pipeline_return, dict)
                assert pipeline_return.get("pipeline_status") == "VERIFICATION_FAILED"
    finally:
        await teardown_db()"""

pattern = r"@pytest\.mark\.asyncio\nasync def test_post_action_verification_fails\(\):.*?finally:\n        await teardown_db\(\)"

new_content = re.sub(pattern, replacer, content, flags=re.DOTALL)
with open("tests/integration/test_failure_paths.py", "w") as f:
    f.write(new_content)
