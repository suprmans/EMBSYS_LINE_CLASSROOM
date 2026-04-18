from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

from .database import init_db
from .webhook import router

# Walk up from line/src/ to find the project-root .env
_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_ROOT / ".env", override=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(router)
