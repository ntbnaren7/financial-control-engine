from pydantic import BaseModel, Field

class LLMConfig(BaseModel):
    """
    Model and runtime configuration for the LLM inference provider.
    """
    model_name: str = Field(..., description="The identifier of the LLM (e.g., phi4-mini:3.8b-q4_K_M)")
    base_url: str = Field(default="http://localhost:11434/v1", description="API base URL (defaults to Ollama local)")
    api_key: str = Field(default="ollama", description="API key if required")
    max_tokens: int = Field(default=2048, description="Maximum tokens for the model to generate")
    num_ctx: int = Field(default=8192, description="Context window size")
    temperature: float = Field(default=0.0, description="Temperature for generation (default 0.0 for deterministic evaluation)")
