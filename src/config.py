"""
Configuration — loads API keys and settings from .env via pydantic-settings.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # API Keys
    gemini_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # Zoho Books
    zoho_client_id: str = ""
    zoho_client_secret: str = ""
    zoho_refresh_token: str = ""
    zoho_organization_id: str = ""
    zoho_redirect_uri: str = "https://www.zoho.com/books/"

    # Extraction defaults
    default_model: str = "gemini-2.5-flash"


settings = Settings()
