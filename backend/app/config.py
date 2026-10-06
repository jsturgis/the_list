from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""

    # Public Drive file (maintained by the Apps Script) pointing at the newest formatted edition.
    drive_latest_file_id: str = ""

    ollama_base_url: str = "http://localhost:11434"
    ollama_embedding_model: str = "nomic-embed-text"

    database_url: str = "sqlite:///./the_list.db"
    faiss_index_path: str = "./data/faiss"
    # Band photos, kept with the data (app/ingestion/band_photos.py); on the data branch next to the database.
    images_path: str = "./data/images"

    musicbrainz_app_name: str = "the-list"
    musicbrainz_app_version: str = "0.1"
    musicbrainz_contact: str = "https://github.com/jsturgis/the_list"
    # Last.fm, for genre tags (app/ingestion/lastfm.py); without a key Last.fm is skipped.
    lastfm_api_key: str | None = None

    google_maps_api_key: str = ""

    data_retention_days: int = 90

    # Calendar dates ("today", upcoming vs past) are evaluated in this timezone.
    timezone: str = "America/Los_Angeles"

    # Weekly Alerts (ADR 0003): people and their Saved Filters live in Supabase. The key is the project's
    # secret key (sb_secret_...), which reads every row; it's only ever a GitHub secret or a local .env value.
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    # Where links in the Alert emails point.
    site_url: str = "https://list.sturgis.me"
    # Alert emails are sent through Resend, from a domain verified there (list.sturgis.me).
    resend_api_key: str = ""
    alerts_from: str = "The List <alerts@list.sturgis.me>"


settings = Settings()
