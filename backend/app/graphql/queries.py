from __future__ import annotations
import strawberry
from strawberry.types import Info

from app.graphql.types import BandType, ShowFilters, ShowType


@strawberry.type
class Query:
    @strawberry.field
    def shows(
        self,
        info: Info,
        filters: ShowFilters | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ShowType]:
        # TODO: implement filtered DB query
        raise NotImplementedError

    @strawberry.field
    def show(self, info: Info, id: strawberry.ID) -> ShowType | None:
        # TODO: implement
        raise NotImplementedError

    @strawberry.field
    def bands(self, info: Info, query: str, limit: int = 20) -> list[BandType]:
        # TODO: SQLite LIKE '%query%' on Band.name
        raise NotImplementedError

    @strawberry.field
    def band(self, info: Info, id: strawberry.ID) -> BandType | None:
        # TODO: implement
        raise NotImplementedError

    @strawberry.field
    def similar_bands(
        self, info: Info, band_id: strawberry.ID, k: int = 10
    ) -> list[BandType]:
        # TODO: deserialise Band.embedding → find_similar_bands → fetch Band records
        raise NotImplementedError

    @strawberry.field
    def similar_shows(
        self, info: Info, show_id: strawberry.ID, k: int = 10
    ) -> list[ShowType]:
        # TODO: deserialise Show.embedding → find_similar_shows → fetch upcoming Show records
        raise NotImplementedError
