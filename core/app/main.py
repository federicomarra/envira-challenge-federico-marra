import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.db import engine
from app.load import load
from app.loss_experience import router
from app.report import router as report_router


@asynccontextmanager
async def lifespan(app):
    load(engine, os.environ["DATA_DIR"])
    yield


app = FastAPI(title="Envira loss experience", lifespan=lifespan)
app.include_router(router)
app.include_router(report_router)


@app.get("/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok", "db": "ok"}
