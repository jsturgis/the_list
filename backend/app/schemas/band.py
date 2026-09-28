from pydantic import BaseModel


class BandRead(BaseModel):
    id: int
    name: str
    genres: list[str] = []
    spotify_url: str | None = None
    soundcloud_url: str | None = None
    description: str | None = None

    model_config = {"from_attributes": True}
