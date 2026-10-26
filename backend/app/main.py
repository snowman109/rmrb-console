import csv
import io
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import config, db, parser
from app.worker import RunWorker

FRONTEND_DIST = config.PROJECT_DIR / "frontend" / "dist"

worker = RunWorker(config.load_config)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init_db()
    db.mark_interrupted_runs()
    worker.start()
    yield


app = FastAPI(title="AVD 归因测试控制台", lifespan=lifespan)


class StartRunBody(BaseModel):
    url: str = Field(min_length=1)
    rounds: int = Field(ge=1, le=1000)
    avd: Optional[str] = None


@app.get("/api/config")
def get_config() -> dict:
    return config.load_config()


@app.put("/api/config")
def put_config(updates: dict) -> dict:
    return config.save_config(updates)


@app.get("/api/avds")
def list_avds() -> list:
    avd_dir = Path.home() / ".android" / "avd"
    if not avd_dir.is_dir():
        return []
    return sorted(p.stem for p in avd_dir.glob("*.ini"))


@app.post("/api/runs")
def start_run(body: StartRunBody) -> dict:
    url = body.url.strip()
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=422,
                            detail="url must start with http:// or https://")
    cfg = config.load_config()
    run_id = worker.submit(url, body.rounds, body.avd or cfg["default_avd"])
    return {"id": run_id}


@app.get("/api/runs")
def get_runs(limit: int = 50, offset: int = 0) -> list:
    return db.list_runs(limit, offset)


@app.get("/api/runs/{run_id}")
def get_run(run_id: int) -> dict:
    run = db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return {"run": run, "counts": db.count_rounds_by_status(run_id)}


@app.get("/api/runs/{run_id}/rounds")
def get_rounds(run_id: int) -> list:
    if db.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="run not found")
    return db.list_rounds(run_id)


@app.get("/api/runs/{run_id}/events")
def get_events(run_id: int, after_id: int = 0) -> list:
    if db.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="run not found")
    return [e for e in db.list_events(run_id) if e["id"] > after_id]


@app.get("/api/runs/{run_id}/logs")
def get_logs(run_id: int, after_seq: int = -1, limit: int = 2000) -> list:
    if db.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="run not found")
    return db.list_log_lines(run_id, after_seq)[:limit]


@app.post("/api/runs/{run_id}/cancel")
def cancel_run(run_id: int) -> dict:
    if db.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="run not found")
    return {"canceled": worker.cancel(run_id)}


@app.get("/api/runs/{run_id}/export.csv")
def export_csv(run_id: int):
    if db.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="run not found")
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["round"] + parser.CSV_COLUMNS)
    for row in db.list_rounds(run_id):
        writer.writerow([row["round_no"]] + [row[name] for name in parser.CSV_COLUMNS])
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="run_{run_id}.csv"'},
    )


if FRONTEND_DIST.exists():
    assets = FRONTEND_DIST / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        candidate = FRONTEND_DIST / path
        if path and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(FRONTEND_DIST / "index.html"))
else:
    @app.get("/")
    def index_placeholder() -> dict:
        return {"message": "frontend 未构建：在 frontend/ 下执行 npm install && npm run build"}