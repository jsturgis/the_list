from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""

    gmail_credentials_path: str = "credentials.json"
    gmail_token_path: str = "token.json"
    gmail_watch_email: str = "skoepke@stevelist.com"

    ollama_base_url: str = "http://localhost:11434"
    ollama_embedding_model: str = "nomic-embed-text"

    database_url: str = "sqlite:///./the_list.db"
    faiss_index_path: str = "./data/faiss"

    spotify_client_id: str = ""
    spotify_client_secret: str = ""

    data_retention_days: int = 90


settings = Settings()
