import strawberry
from strawberry.types import Info


@strawberry.type
class Mutation:
    @strawberry.mutation
    def start_ingestion(self, info: Info) -> str:
        # TODO: fire run_ingestion_pipeline as a BackgroundTasks task
        raise NotImplementedError
