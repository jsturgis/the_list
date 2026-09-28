from pydantic import BaseModel

from app.models.venue import Region


class VenueRead(BaseModel):
    id: int
    name: str
    address: str | None = None
    city: str
    region: Region
    website_url: str | None = None

    model_config = {"from_attributes": True}
