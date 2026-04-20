from pathlib import Path
from dotenv import load_dotenv

# Must load before any relative imports that read os.environ at module level
_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_ROOT / ".env", override=True)

from contextlib import asynccontextmanager
from fastapi import FastAPI
from .database import init_db
from .webhook import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(router)
