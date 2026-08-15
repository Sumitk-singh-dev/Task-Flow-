"""
crud.py — Database CRUD helpers for TaskFlow.
All aggregation queries execute in the database, not in Python.
"""
from typing import List, Optional
from sqlalchemy import func, case
from sqlalchemy.orm import Session
from passlib.context import CryptContext

import models
import schemas

# ── Password hashing ─────────────────────────────────────────────────────────
# bcrypt is a strong, slow hashing algorithm — ideal for passwords.
# Never store plain-text passwords; always hash before saving.
#
# passlib 1.7.4 logs a harmless warning about bcrypt 4.x's changed __about__
# attribute. We suppress it here so the server logs stay clean.
import warnings
warnings.filterwarnings("ignore", ".*error reading bcrypt version.*")
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """Return the bcrypt hash of a plain-text password."""
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if plain matches the stored hash (for future login use)."""
    return _pwd_context.verify(plain, hashed)


# ─────────────────────────────────────────────────────────────────────────────
# Users
# ─────────────────────────────────────────────────────────────────────────────

def get_user(db: Session, user_id: int) -> Optional[models.User]:
    return db.get(models.User, user_id)


def get_user_by_email(db: Session, email: str) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.email == email).first()


def get_users(db: Session, skip: int = 0, limit: int = 100) -> List[models.User]:
    return db.query(models.User).offset(skip).limit(limit).all()


def create_user(db: Session, payload: schemas.UserCreate) -> models.User:
    user = models.User(
        name=payload.name,
        email=payload.email,
        password=hash_password(payload.password),   # Always hash the password!
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def delete_user(db: Session, user_id: int) -> bool:
    user = db.get(models.User, user_id)
    if not user:
        return False
    db.delete(user)
    db.commit()
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Projects
# ─────────────────────────────────────────────────────────────────────────────

def get_project(db: Session, project_id: int) -> Optional[models.Project]:
    return db.get(models.Project, project_id)


def get_projects(db: Session, skip: int = 0, limit: int = 100) -> List[models.Project]:
    return db.query(models.Project).offset(skip).limit(limit).all()


def get_projects_by_owner(db: Session, owner_id: int) -> List[models.Project]:
    return db.query(models.Project).filter(models.Project.owner_id == owner_id).all()


def create_project(db: Session, payload: schemas.ProjectCreate) -> models.Project:
    project = models.Project(
        name=payload.name,
        description=payload.description,
        owner_id=payload.owner_id,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def delete_project(db: Session, project_id: int) -> bool:
    project = db.get(models.Project, project_id)
    if not project:
        return False
    db.delete(project)
    db.commit()
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Tasks
# ─────────────────────────────────────────────────────────────────────────────

def get_task(db: Session, task_id: int) -> Optional[models.Task]:
    return db.get(models.Task, task_id)


def get_tasks(
    db: Session,
    project_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
) -> List[models.Task]:
    q = db.query(models.Task)
    if project_id is not None:
        q = q.filter(models.Task.project_id == project_id)
    return q.offset(skip).limit(limit).all()


def create_task(db: Session, payload: schemas.TaskCreate) -> models.Task:
    task = models.Task(
        title=payload.title,
        description=payload.description,
        status=payload.status,
        priority=payload.priority,
        due_date=payload.due_date,
        project_id=payload.project_id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def update_task(db: Session, task_id: int, payload: schemas.TaskUpdate) -> Optional[models.Task]:
    task = db.get(models.Task, task_id)
    if not task:
        return None
    # Only update fields that were actually sent in the request
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(task, field, value)
    db.commit()
    db.refresh(task)
    return task


def delete_task(db: Session, task_id: int) -> bool:
    task = db.get(models.Task, task_id)
    if not task:
        return False
    db.delete(task)
    db.commit()
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Aggregate stats — computed entirely in SQL via COUNT + GROUP BY
# ─────────────────────────────────────────────────────────────────────────────

def get_project_stats(db: Session) -> List[schemas.ProjectStats]:
    """
    Return per-project task counts broken down by status.
    The aggregation (COUNT, conditional COUNT) runs as a single SQL query
    with a JOIN and GROUP BY — no Python-side aggregation.
    """
    rows = (
        db.query(
            models.Project.id.label("project_id"),
            models.Project.name.label("project_name"),
            func.count(models.Task.id).label("total_tasks"),
            func.count(
                case((models.Task.status == "todo", models.Task.id), else_=None)
            ).label("todo"),
            func.count(
                case((models.Task.status == "in_progress", models.Task.id), else_=None)
            ).label("in_progress"),
            func.count(
                case((models.Task.status == "done", models.Task.id), else_=None)
            ).label("done"),
        )
        .outerjoin(models.Task, models.Task.project_id == models.Project.id)
        .group_by(models.Project.id, models.Project.name)
        .all()
    )

    return [
        schemas.ProjectStats(
            project_id=r.project_id,
            project_name=r.project_name,
            total_tasks=r.total_tasks,
            todo=r.todo,
            in_progress=r.in_progress,
            done=r.done,
        )
        for r in rows
    ]


def get_single_project_stats(db: Session, project_id: int) -> Optional[schemas.ProjectStats]:
    row = (
        db.query(
            models.Project.id.label("project_id"),
            models.Project.name.label("project_name"),
            func.count(models.Task.id).label("total_tasks"),
            func.count(
                case((models.Task.status == "todo", models.Task.id), else_=None)
            ).label("todo"),
            func.count(
                case((models.Task.status == "in_progress", models.Task.id), else_=None)
            ).label("in_progress"),
            func.count(
                case((models.Task.status == "done", models.Task.id), else_=None)
            ).label("done"),
        )
        .outerjoin(models.Task, models.Task.project_id == models.Project.id)
        .filter(models.Project.id == project_id)
        .group_by(models.Project.id, models.Project.name)
        .first()
    )
    if not row:
        return None
    return schemas.ProjectStats(
        project_id=row.project_id,
        project_name=row.project_name,
        total_tasks=row.total_tasks,
        todo=row.todo,
        in_progress=row.in_progress,
        done=row.done,
    )
