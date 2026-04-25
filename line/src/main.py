# Copyright 2026 Shalong Samretngan
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
from pathlib import Path
from dotenv import load_dotenv

# Must load before any relative imports that read os.environ at module level
_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_ROOT / ".env", override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s [%(name)s] %(message)s",
)

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
