import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(name)s: %(message)s")
logging.getLogger("musicbrainzngs").setLevel(logging.WARNING)
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.graphql.schema import graphql_router
from app.scheduler import scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="The List API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(graphql_router, prefix="/graphql")
