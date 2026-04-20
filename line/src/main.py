from pathlib import Path
from dotenv import load_dotenv

# Must load before any relative imports that read os.environ at module level
_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_ROOT / ".env", override=True)

from contextlib import asynccontextmanager
from fastapi import FastAPI
from .core.database import init_db
from .v1.webhook import router as webhook_v1
from .v1.api import router as api_v1


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Smart Classroom Attendance",
    description=(
        "LINE Beacon attendance backend — BusinessCase01.\n\n"
        "**Lecturer endpoints** require `Authorization: Bearer <LECTURER_TOKEN>`.\n"
        "Set the token in `/docs` via the 🔒 Authorize button."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(webhook_v1)
app.include_router(api_v1)
