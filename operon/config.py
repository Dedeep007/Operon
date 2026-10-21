"""Configuration management for Operon Autonomous AI Task Worker."""

import os
from pathlib import Path
from typing import List
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
SAMPLE_DATA_DIR = BASE_DIR / "operon" / "environment" / "sample_data"
STORAGE_DIR = BASE_DIR / "storage"

class OperonSettings(BaseModel):
    """Runtime configuration for Operon."""
    
    # Model and Provider
    model_name: str = Field(default_factory=lambda: os.getenv("OPERON_MODEL_NAME", "qwen/qwen3.8-27b"))
    groq_api_key: str = Field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))
    temperature: float = Field(default_factory=lambda: float(os.getenv("OPERON_TEMPERATURE", "0.0")))
    
    # Execution & Safety
    max_retries: int = Field(default_factory=lambda: int(os.getenv("OPERON_MAX_RETRIES", "3")))
    require_human_approval: bool = Field(
        default_factory=lambda: os.getenv("OPERON_HUMAN_IN_THE_LOOP", "true").lower() in ("true", "1", "yes")
    )
    high_risk_tools: List[str] = Field(
        default_factory=lambda: ["erp_delete_record", "erp_bulk_delete", "send_external_email", "execute_payment"]
    )
    
    # Paths
    base_dir: Path = BASE_DIR
    sample_data_dir: Path = SAMPLE_DATA_DIR
    storage_dir: Path = STORAGE_DIR
    
    # Environment
    mock_llm_if_no_key: bool = True
    environment: str = Field(default_factory=lambda: os.getenv("OPERON_ENVIRONMENT", "live"))

settings = OperonSettings()
