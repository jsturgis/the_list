import strawberry
from fastapi import BackgroundTasks, Depends
from sqlalchemy.orm import Session
from strawberry.fastapi import GraphQLRouter

from app.database import get_db
from app.graphql.mutations import Mutation
from app.graphql.queries import Query


async def get_context(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    return {"db": db, "background_tasks": background_tasks}


schema = strawberry.Schema(query=Query, mutation=Mutation)
graphql_router = GraphQLRouter(schema, context_getter=get_context)
