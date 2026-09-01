import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from src.investigation.ai import InvestigationEngine
from src.investigation.models import DiscrepancyContext, EvidenceItem, InvestigationEligibility, ConfidenceBand
from src.investigation.config import LLMConfig
from src.investigation.result import InvestigationStatus
import json

@pytest.mark.asyncio
async def test_engine_api_error():
    engine = InvestigationEngine(config=LLMConfig(model_name="mock-model"))
    with patch.object(engine.client.chat.completions, 'create', new=AsyncMock(side_effect=Exception("API Down"))):
        result = await engine.investigate(
            DiscrepancyContext(case_id="1", description="", provider_status="", merchant_status="", amount_match=True, currency_match=True, identity_verified=True),
            []
        )
        assert result.status == InvestigationStatus.API_ERROR
        assert result.failure_reason is not None
        assert "API Down" in result.failure_reason

@pytest.mark.asyncio
async def test_engine_empty_output():
    engine = InvestigationEngine(config=LLMConfig(model_name="mock-model"))
    
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content=""))]
    
    with patch.object(engine.client.chat.completions, 'create', new=AsyncMock(return_value=mock_response)):
        result = await engine.investigate(
            DiscrepancyContext(case_id="1", description="", provider_status="", merchant_status="", amount_match=True, currency_match=True, identity_verified=True),
            []
        )
        assert result.status == InvestigationStatus.EMPTY_OUTPUT

@pytest.mark.asyncio
async def test_engine_schema_invalid_bad_json():
    engine = InvestigationEngine(config=LLMConfig(model_name="mock-model"))
    
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="{ bad json "))]
    
    with patch.object(engine.client.chat.completions, 'create', new=AsyncMock(return_value=mock_response)):
        result = await engine.investigate(
            DiscrepancyContext(case_id="1", description="", provider_status="", merchant_status="", amount_match=True, currency_match=True, identity_verified=True),
            []
        )
        assert result.status == InvestigationStatus.SCHEMA_INVALID
        assert result.failure_reason is not None
        assert "INVALID_JSON" in result.failure_reason

@pytest.mark.asyncio
async def test_engine_schema_invalid_pydantic():
    engine = InvestigationEngine(config=LLMConfig(model_name="mock-model"))
    
    mock_response = MagicMock()
    # Valid JSON but missing required fields
    mock_response.choices = [MagicMock(message=MagicMock(content='{"eligibility": "ELIGIBLE"}'))]
    
    with patch.object(engine.client.chat.completions, 'create', new=AsyncMock(return_value=mock_response)):
        result = await engine.investigate(
            DiscrepancyContext(case_id="1", description="", provider_status="", merchant_status="", amount_match=True, currency_match=True, identity_verified=True),
            []
        )
        assert result.status == InvestigationStatus.SCHEMA_INVALID
        assert result.failure_reason is not None
        assert "SCHEMA_INVALID" in result.failure_reason

@pytest.mark.asyncio
async def test_engine_invariant_invalid():
    engine = InvestigationEngine(config=LLMConfig(model_name="mock-model"))
    
    mock_response = MagicMock()
    # Let's provide 5 but with duplicate ranks to trigger Invariant invalid.
    content = {
        "eligibility": "ELIGIBLE",
        "overall_confidence": "HIGH",
        "selections": [
            {
                "hypothesis_id": "WEBHOOK_NOT_OBSERVED",
                "rank": 1,
                "rationale": "",
                "confidence_band": "HIGH",
                "supporting_evidence_ids": [],
                "contradicting_evidence_ids": [],
                "missing_evidence_types": []
            },
            {
                "hypothesis_id": "WEBHOOK_OBSERVED_NOT_PROCESSED",
                "rank": 1, # Duplicate rank
                "rationale": "",
                "confidence_band": "HIGH",
                "supporting_evidence_ids": [],
                "contradicting_evidence_ids": [],
                "missing_evidence_types": []
            },
            {
                "hypothesis_id": "WEBHOOK_PROCESSED_STATE_NOT_UPDATED",
                "rank": 3,
                "rationale": "",
                "confidence_band": "HIGH",
                "supporting_evidence_ids": [],
                "contradicting_evidence_ids": [],
                "missing_evidence_types": []
            },
            {
                "hypothesis_id": "PROVIDER_MERCHANT_STATE_REPRESENTATION_MISMATCH",
                "rank": 4,
                "rationale": "",
                "confidence_band": "HIGH",
                "supporting_evidence_ids": [],
                "contradicting_evidence_ids": [],
                "missing_evidence_types": []
            },
            {
                "hypothesis_id": "EVIDENCE_INSUFFICIENT",
                "rank": 5,
                "rationale": "",
                "confidence_band": "HIGH",
                "supporting_evidence_ids": [],
                "contradicting_evidence_ids": [],
                "missing_evidence_types": []
            }
        ]
    }
    
    mock_response.choices = [MagicMock(message=MagicMock(content=json.dumps(content)))]
    
    with patch.object(engine.client.chat.completions, 'create', new=AsyncMock(return_value=mock_response)):
        result = await engine.investigate(
            DiscrepancyContext(case_id="1", description="", provider_status="", merchant_status="", amount_match=True, currency_match=True, identity_verified=True),
            []
        )
        assert result.status == InvestigationStatus.INVARIANT_INVALID

@pytest.mark.asyncio
async def test_engine_accepted():
    engine = InvestigationEngine(config=LLMConfig(model_name="mock-model"))
    
    mock_response = MagicMock()
    content = {
        "eligibility": "ELIGIBLE",
        "overall_confidence": "HIGH",
        "selections": [
            {
                "hypothesis_id": "WEBHOOK_NOT_OBSERVED",
                "rank": 1,
                "rationale": "",
                "confidence_band": "HIGH",
                "supporting_evidence_ids": [],
                "contradicting_evidence_ids": [],
                "missing_evidence_types": []
            },
            {
                "hypothesis_id": "WEBHOOK_OBSERVED_NOT_PROCESSED",
                "rank": 2, 
                "rationale": "",
                "confidence_band": "HIGH",
                "supporting_evidence_ids": [],
                "contradicting_evidence_ids": [],
                "missing_evidence_types": []
            },
            {
                "hypothesis_id": "WEBHOOK_PROCESSED_STATE_NOT_UPDATED",
                "rank": 3,
                "rationale": "",
                "confidence_band": "HIGH",
                "supporting_evidence_ids": [],
                "contradicting_evidence_ids": [],
                "missing_evidence_types": []
            },
            {
                "hypothesis_id": "PROVIDER_MERCHANT_STATE_REPRESENTATION_MISMATCH",
                "rank": 4,
                "rationale": "",
                "confidence_band": "HIGH",
                "supporting_evidence_ids": [],
                "contradicting_evidence_ids": [],
                "missing_evidence_types": []
            },
            {
                "hypothesis_id": "EVIDENCE_INSUFFICIENT",
                "rank": 5,
                "rationale": "",
                "confidence_band": "HIGH",
                "supporting_evidence_ids": [],
                "contradicting_evidence_ids": [],
                "missing_evidence_types": []
            }
        ]
    }
    
    mock_response.choices = [MagicMock(message=MagicMock(content=json.dumps(content)))]
    
    with patch.object(engine.client.chat.completions, 'create', new=AsyncMock(return_value=mock_response)):
        result = await engine.investigate(
            DiscrepancyContext(case_id="1", description="", provider_status="", merchant_status="", amount_match=True, currency_match=True, identity_verified=True),
            []
        )
        assert result.status == InvestigationStatus.ACCEPTED
        assert result.proposal is not None

@pytest.mark.asyncio
async def test_engine_strips_think_tags_safely():
    engine = InvestigationEngine(config=LLMConfig(model_name="mock-model"))
    
    mock_response = MagicMock()
    content_with_think = """<think>
    Here is my thought process:
    ```json
    {
        "internal_state": "thinking"
    }
    ```
    </think>
    {
        "eligibility": "ELIGIBLE",
        "overall_confidence": "HIGH",
        "selections": [
            {
                "hypothesis_id": "WEBHOOK_NOT_OBSERVED",
                "rank": 1,
                "rationale": "",
                "confidence_band": "HIGH",
                "supporting_evidence_ids": [],
                "contradicting_evidence_ids": [],
                "missing_evidence_types": []
            },
            {
                "hypothesis_id": "WEBHOOK_OBSERVED_NOT_PROCESSED",
                "rank": 2, 
                "rationale": "",
                "confidence_band": "HIGH",
                "supporting_evidence_ids": [],
                "contradicting_evidence_ids": [],
                "missing_evidence_types": []
            },
            {
                "hypothesis_id": "WEBHOOK_PROCESSED_STATE_NOT_UPDATED",
                "rank": 3,
                "rationale": "",
                "confidence_band": "HIGH",
                "supporting_evidence_ids": [],
                "contradicting_evidence_ids": [],
                "missing_evidence_types": []
            },
            {
                "hypothesis_id": "PROVIDER_MERCHANT_STATE_REPRESENTATION_MISMATCH",
                "rank": 4,
                "rationale": "",
                "confidence_band": "HIGH",
                "supporting_evidence_ids": [],
                "contradicting_evidence_ids": [],
                "missing_evidence_types": []
            },
            {
                "hypothesis_id": "EVIDENCE_INSUFFICIENT",
                "rank": 5,
                "rationale": "",
                "confidence_band": "HIGH",
                "supporting_evidence_ids": [],
                "contradicting_evidence_ids": [],
                "missing_evidence_types": []
            }
        ]
    }
    """
    
    mock_response.choices = [MagicMock(message=MagicMock(content=content_with_think))]
    
    with patch.object(engine.client.chat.completions, 'create', new=AsyncMock(return_value=mock_response)):
        result = await engine.investigate(
            DiscrepancyContext(case_id="1", description="", provider_status="", merchant_status="", amount_match=True, currency_match=True, identity_verified=True),
            []
        )
        assert result.status == InvestigationStatus.ACCEPTED
        assert result.proposal is not None
        assert result.proposal.eligibility.value == "ELIGIBLE"
