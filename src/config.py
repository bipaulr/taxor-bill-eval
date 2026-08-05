"""
Configuration — loads API keys and settings from .env via pydantic-settings.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # API Keys
    gemini_api_key: str = ""
    openrouter_api_key: str = ""

    # Zoho Books
    zoho_client_id: str = ""
    zoho_client_secret: str = ""
    zoho_refresh_token: str = ""
    zoho_organization_id: str = ""
    zoho_redirect_uri: str = "https://www.zoho.com/books/"
    # Data center region: com (US/Global), in (India), eu (Europe), au (Australia), cn (China)
    zoho_data_center: str = "in"
    # Expense account to book extracted bills under (must exist in the org's chart of accounts)
    zoho_expense_account: str = "Uncategorized"

    # Extraction defaults
    default_model: str = "gemini-2.5-flash"


settings = Settings()
