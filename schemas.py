"""
schemas.py — Pydantic v2 request/response models for TaskFlow.
"""
from __future__ import annotations
from typing import Literal, Optional, List
from pydantic import BaseModel, EmailStr, Field, field_validator


# ── Priority / Status enums as Literal types ─────────────────────────────────
Priority = Literal["low", "medium", "high"]
Status   = Literal["todo", "in_progress", "done"]


# ─────────────────────────────────────────────────────────────────────────────
# User schemas
# ─────────────────────────────────────────────────────────────────────────────
class UserCreate(BaseModel):
    name:     str      = Field(..., min_length=1, max_length=120)
    email:    EmailStr = Field(...)          # EmailStr validates format properly
    password: str      = Field(..., min_length=6)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be blank")
        return v.strip()

    # EmailStr already normalises the address; we just lowercase for storage
    @field_validator("email", mode="before")
    @classmethod
    def email_lowercase(cls, v: str) -> str:
        return v.strip().lower()


class UserOut(BaseModel):
    id:    int
    name:  str
    email: str

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# Project schemas
# ─────────────────────────────────────────────────────────────────────────────
class ProjectCreate(BaseModel):
    name:        str            = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    owner_id:    int

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("project name must not be blank")
        return v.strip()


class ProjectOut(BaseModel):
    id:          int
    name:        str
    description: Optional[str]
    owner_id:    int

    model_config = {"from_attributes": True}


class ProjectWithStats(ProjectOut):
    total_tasks: int
    todo:        int
    in_progress: int
    done:        int


# ─────────────────────────────────────────────────────────────────────────────
# Task schemas
# ─────────────────────────────────────────────────────────────────────────────
class TaskCreate(BaseModel):
    title:       str            = Field(..., min_length=1, max_length=300)
    description: Optional[str] = Field(None, max_length=2000)
    status:      Status         = Field("todo")
    priority:    Priority       = Field("medium")
    due_date:    Optional[str]  = Field(None, max_length=100)
    project_id:  int

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("title must not be blank or whitespace-only")
        return stripped

    @field_validator("description")
    @classmethod
    def description_strip(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            return v if v else None
        return v

    @field_validator("due_date")
    @classmethod
    def due_date_not_only_digits(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if v.isdigit():
                raise ValueError(
                    "due_date looks invalid — provide a date or phrase like 'next friday'"
                )
        return v if v else None


class TaskUpdate(BaseModel):
    title:       Optional[str]      = Field(None, min_length=1, max_length=300)
    description: Optional[str]      = Field(None, max_length=2000)
    status:      Optional[Status]   = None
    priority:    Optional[Priority] = None
    due_date:    Optional[str]      = Field(None, max_length=100)

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError("title must not be blank")
        return v.strip() if v else v


class TaskOut(BaseModel):
    id:          int
    title:       str
    description: Optional[str]
    status:      str
    priority:    str
    due_date:    Optional[str]
    project_id:  int

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# Quick Add schema
# ─────────────────────────────────────────────────────────────────────────────

class QuickAddRequest(BaseModel):
    """
    Request body for POST /tasks/quick-add.
    The free-text description is parsed by the deterministic mock parser
    (or optionally a real LLM) to infer title, priority, and due_date.
    """
    description: str  = Field(..., min_length=1, max_length=2000,
                               description="Free-text task description")
    project_id:  int  = Field(..., description="ID of the project to associate the task with")

    @field_validator("description")
    @classmethod
    def description_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("description must not be blank or whitespace-only")
        return v


# ─────────────────────────────────────────────────────────────────────────────
# Stats schema
# ─────────────────────────────────────────────────────────────────────────────
class ProjectStats(BaseModel):
    project_id:   int
    project_name: str
    total_tasks:  int
    todo:         int
    in_progress:  int
    done:         int
