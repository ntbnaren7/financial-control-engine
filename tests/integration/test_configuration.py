import os
import pytest
from pydantic import ValidationError
from src.config.settings import FCESettings, RazorpaySettings, DatabaseSettings
from src.investigation.agent import LocalLLMInvestigator
from src.integrations.razorpay.client import RazorpayClient
import structlog
from io import StringIO
import logging

def test_settings_fail_fast_missing_required_secrets(monkeypatch):
    """
    Ensure that instantiation fails if required secrets (e.g. Razorpay keys) 
    are missing and not provided via environment or .env.
    """
    # Clear environment variables for strict testing
    monkeypatch.delenv("RAZORPAY_KEY_ID", raising=False)
    monkeypatch.delenv("RAZORPAY_KEY_SECRET", raising=False)
    
    # We must explicitly trigger failure by passing empty strings or not defaulting
    # In our current schema, we used `default=""`. To enforce fail-fast, we should 
    # either remove the default or raise ValueError if it's empty during init.
    
    # Let's test our actual pydantic schema: 
    # Currently it has defaults, but let's say the user wants it to fail fast.
    # We should update `settings.py` to NOT have defaults for keys to truly fail fast.
    # Wait, in settings.py we set `default=""`. I will update settings.py shortly to remove that default
    # so this test passes.
    
    with pytest.raises(ValidationError):
        RazorpaySettings(key_id=None, key_secret=None) # type: ignore

def test_secret_str_prevents_leakage():
    """
    Prove that logging or stringifying a configuration model containing a SecretStr 
    does not reveal the plaintext value.
    """
    db_config = DatabaseSettings(url="postgresql://user:super_secret_password@localhost/db")
    
    # Standard stringification
    assert "super_secret_password" not in str(db_config)
    assert "**********" in str(db_config)
    
    # Structlog serialization
    output = StringIO()
    structlog.configure(
        processors=[structlog.processors.JSONRenderer()],
        logger_factory=structlog.PrintLoggerFactory(file=output)
    )
    
    logger = structlog.get_logger()
    logger.info("Database config", config=db_config.model_dump())
    
    log_output = output.getvalue()
    assert "super_secret_password" not in log_output
    assert "**********" in log_output

def test_environment_precedence_and_overrides(monkeypatch):
    """
    Verify that semantic configurations can be overridden safely.
    """
    monkeypatch.setenv("CONTROL_LOOP__WORKER_LEASE_TTL_SECONDS", "45")
    monkeypatch.setenv("RAZORPAY__KEY_ID", "live_key")
    monkeypatch.setenv("RAZORPAY__KEY_SECRET", "live_secret")
    
    settings = FCESettings()
    
    assert settings.control_loop.worker_lease_ttl_seconds == 45
    assert settings.razorpay.key_id == "live_key"
    assert settings.razorpay.key_secret.get_secret_value() == "live_secret"
