import os
from pydantic import BaseModel

class Settings(BaseModel):
    data_dir: str = os.getenv("LAPTOP_AGENTS_DATA_DIR", "src/laptop_agents/data")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")

def get_settings() -> Settings:
    return Settings()
