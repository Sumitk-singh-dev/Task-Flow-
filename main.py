"""
main.py — FastAPI application for TaskFlow.
 
Includes:
  • Lifespan handler (replaces deprecated @app.on_event)
  • Custom timing middleware (logs method + path + ms on every request)
  • CORS middleware — allows all common dev origins
  • get_db() dependency reused across all endpoint groups
  • Full CRUD for tasks, projects, and users
  • GET /stats — per-project task statistics via SQL aggregation
  • GET /health — quick liveness check
"""
import time
import logging
from contextlib import asynccontextmanager
 
from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Optional
 
import crud
import schemas
from database import get_db, init_db
from quick_add import parse_task_description
 
# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("taskflow")
 
 
# ── Lifespan (replaces deprecated @app.on_event("startup")) ──────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Code before `yield` runs on startup.
    Code after `yield` runs on shutdown.
    """
    init_db()
    logger.info("Database initialised.")
    yield
    logger.info("Application shutting down.")
 
 
# ── App init ──────────────────────────────────────────────────────────────────
app = FastAPI(
    title="TaskFlow API",
    description="AI-Assisted Task Management Platform",
    version="1.0.0",
    lifespan=lifespan,
)
 
 
# ── CORS ──────────────────────────────────────────────────────────────────────
# Allow all typical local development origins.
# The frontend can be opened directly as a file (file://) or via a dev server
# on various ports (5500, 3000, 8080, 4200, etc.).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:4200",
        "http://127.0.0.1:4200",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept"],
)
 
 
# ── Custom timing middleware ──────────────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log HTTP method, path, and processing time (ms) for every request."""
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "%s %s  →  %d  (%.2f ms)",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    
    # NOTE: This API's GET endpoints (/tasks, /projects, /users, /stats) all
    # reflect data that other requests can mutate at any time (create/update/
    # delete). Caching them with max-age let the browser silently reuse a
    # stale response after a delete/update, so deleted/changed rows kept
    # appearing in the UI until the cache window expired or the page was
    # hard-refreshed. Explicitly disabling caching keeps every GET fresh.
    if request.method == "GET":
        response.headers["Cache-Control"] = "no-store"
    
    return response
 
 
# ═════════════════════════════════════════════════════════════════════════════
# Users  —  POST /users,  GET /users,  GET /users/{id}
# ═════════════════════════════════════════════════════════════════════════════
 
@app.post(
    "/users",
    response_model=schemas.UserOut,
    status_code=status.HTTP_201_CREATED,
    tags=["users"],
    summary="Create a new user",
)
def create_user(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    if crud.get_user_by_email(db, payload.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Email '{payload.email}' is already registered.",
        )
    return crud.create_user(db, payload)
 
@app.get(
    "/users",
    response_model=List[schemas.UserOut],
    tags=["users"],
    summary="List all users",
)
def list_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_users(db, skip=skip, limit=limit)
 
 
@app.get(
    "/users/{user_id}",
    response_model=schemas.UserOut,
    tags=["users"],
    summary="Get a single user by ID",
)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return user
 
 
@app.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["users"],
    summary="Delete a user (and their projects and tasks)",
)
def delete_user(user_id: int, db: Session = Depends(get_db)):
    if not crud.delete_user(db, user_id):
        raise HTTPException(status_code=404, detail="User not found.")
 
 
# ═════════════════════════════════════════════════════════════════════════════
# Projects  —  POST /projects,  GET /projects,  GET /projects/{id},
#              DELETE /projects/{id}
# ═════════════════════════════════════════════════════════════════════════════
 
@app.post(
    "/projects",
    response_model=schemas.ProjectOut,
    status_code=status.HTTP_201_CREATED,
    tags=["projects"],
    summary="Create a new project",
)
def create_project(payload: schemas.ProjectCreate, db: Session = Depends(get_db)):
    if not crud.get_user(db, payload.owner_id):
        raise HTTPException(status_code=404, detail="Owner user not found.")
    return crud.create_project(db, payload)
 
 
@app.get(
    "/projects",
    response_model=List[schemas.ProjectOut],
    tags=["projects"],
    summary="List all projects",
)
def list_projects(
    owner_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    if owner_id is not None:
        return crud.get_projects_by_owner(db, owner_id)
    return crud.get_projects(db, skip=skip, limit=limit)
 
 
@app.get(
    "/projects/{project_id}",
    response_model=schemas.ProjectOut,
    tags=["projects"],
    summary="Get a single project by ID",
)
def get_project(project_id: int, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project
 
 
@app.delete(
    "/projects/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["projects"],
    summary="Delete a project (and all its tasks)",
)
def delete_project(project_id: int, db: Session = Depends(get_db)):
    if not crud.delete_project(db, project_id):
        raise HTTPException(status_code=404, detail="Project not found.")
 
 
# ═════════════════════════════════════════════════════════════════════════════
# Tasks  —  full CRUD
# POST   /tasks          → 201
# GET    /tasks          → 200  (optionally filtered by ?project_id=)
# GET    /tasks/{id}     → 200 | 404
# PUT    /tasks/{id}     → 200 | 404 | 422
# DELETE /tasks/{id}     → 204 | 404
# ═════════════════════════════════════════════════════════════════════════════
 
@app.post(
    "/tasks",
    response_model=schemas.TaskOut,
    status_code=status.HTTP_201_CREATED,
    tags=["tasks"],
    summary="Create a new task",
)
def create_task(payload: schemas.TaskCreate, db: Session = Depends(get_db)):
    if not crud.get_project(db, payload.project_id):
        raise HTTPException(status_code=404, detail="Project does not exist.")
    return crud.create_task(db, payload)
 
 
@app.get(
    "/tasks",
    response_model=List[schemas.TaskOut],
    tags=["tasks"],
    summary="List all tasks (optionally filter by project)",
)
def list_tasks(
    project_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    return crud.get_tasks(db, project_id=project_id, skip=skip, limit=limit)
 
 
@app.post(
    "/tasks/quick-add",
    response_model=schemas.TaskOut,
    status_code=status.HTTP_201_CREATED,
    tags=["tasks"],
    summary="Create a task from a free-text description",
    description=(
        "Accepts a plain-English sentence and infers title, priority, and due_date "
        "using a deterministic parser (or optionally a real LLM via USE_REAL_LLM env flag). "
        "The task is stored in the same `tasks` table as all other tasks."
    ),
)
def quick_add_task(payload: schemas.QuickAddRequest, db: Session = Depends(get_db)):
    """
    POST /tasks/quick-add
 
    Flow:
      1. Validate request body (Pydantic).
      2. Verify project exists — 422 if not.
      3. Parse description → title, priority, due_date_hint.
      4. Build TaskCreate payload and validate against TaskOut schema.
      5. Insert row; return 201.
    """
    # ── Step 2: verify project exists ─────────────────────────────────────────
    if not crud.get_project(db, payload.project_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Project with id={payload.project_id} does not exist.",
        )
 
    # ── Step 3: parse the free-text description ────────────────────────────────
    parsed = parse_task_description(payload.description)
 
    # ── Step 4: build and validate the task data before touching the DB ────────
    task_data = schemas.TaskCreate(
        title=parsed["title"],
        description=payload.description,   # keep original text as task description
        status="todo",
        priority=parsed["priority"],
        due_date=parsed["due_date_hint"],   # stored as raw phrase, e.g. "next friday"
        project_id=payload.project_id,
    )
 
    # Validate the data against the TaskOut response model before inserting.
    # This catches any mismatch (e.g. invalid priority value) before a DB write.
    try:
        schemas.TaskOut.model_validate({
            "id": 0,                        # placeholder — not yet assigned
            "title":       task_data.title,
            "description": task_data.description,
            "status":      task_data.status,
            "priority":    task_data.priority,
            "due_date":    task_data.due_date,
            "project_id":  task_data.project_id,
        })
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
 
    # ── Step 5: persist and return ─────────────────────────────────────────────
    task = crud.create_task(db, task_data)
    return task
 
 
@app.get(
    "/tasks/{task_id}",
    response_model=schemas.TaskOut,
    tags=["tasks"],
    summary="Get a single task by ID",
)
def get_task(task_id: int, db: Session = Depends(get_db)):
    task = crud.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task
 
 
@app.put(
    "/tasks/{task_id}",
    response_model=schemas.TaskOut,
    tags=["tasks"],
    summary="Update a task",
)
def update_task(task_id: int, payload: schemas.TaskUpdate, db: Session = Depends(get_db)):
    task = crud.update_task(db, task_id, payload)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task
 
 
@app.delete(
    "/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["tasks"],
    summary="Delete a task",
)
def delete_task(task_id: int, db: Session = Depends(get_db)):
    if not crud.delete_task(db, task_id):
        raise HTTPException(status_code=404, detail="Task not found.")
 
 
# ═════════════════════════════════════════════════════════════════════════════
# Stats  —  GET /stats              (all projects)
#           GET /stats/{project_id} (single project)
# ═════════════════════════════════════════════════════════════════════════════
 
@app.get(
    "/stats",
    response_model=List[schemas.ProjectStats],
    tags=["stats"],
    summary="Task counts per project",
)
def all_project_stats(db: Session = Depends(get_db)):
    """Return task-count-by-status for every project in one SQL query."""
    return crud.get_project_stats(db)
 
 
@app.get(
    "/stats/{project_id}",
    response_model=schemas.ProjectStats,
    tags=["stats"],
    summary="Task counts for a single project",
)
def single_project_stats(project_id: int, db: Session = Depends(get_db)):
    stats = crud.get_single_project_stats(db, project_id)
    if not stats:
        raise HTTPException(status_code=404, detail="Project not found.")
    return stats
 
# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["meta"], summary="Liveness check")
def health():
    return {"status": "ok", "service": "TaskFlow API"}