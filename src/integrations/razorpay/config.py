from pydantic_settings import BaseSettings, SettingsConfigDict

class RazorpaySettings(BaseSettings):
    key_id: str
    key_secret: str
    webhook_secret: str = ""
    
    model_config = SettingsConfigDict(env_prefix='RAZORPAY_', env_file='.env', extra='ignore')

settings = RazorpaySettings()
