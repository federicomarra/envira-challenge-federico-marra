import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import create_engine, text

from app.load import load

engine = create_engine(os.environ["DATABASE_URL"])


@asynccontextmanager
async def lifespan(app):
    load(engine, os.environ["DATA_DIR"])
    yield


app = FastAPI(title="Envira loss experience", lifespan=lifespan)


@app.get("/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok", "db": "ok"}
