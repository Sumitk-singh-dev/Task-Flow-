"""
models.py — SQLAlchemy ORM models for TaskFlow.
Tables: users, projects, tasks
"""
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Text, ForeignKey,
    CheckConstraint, DateTime
)
from sqlalchemy.orm import relationship, DeclarativeBase


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String(120), nullable=False)
    email      = Column(String(255), nullable=False, unique=True, index=True)
    password   = Column(String(255), nullable=False)        # stored as bcrypt hash
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # One user → many projects
    # passive_deletes=True: let the database's ON DELETE CASCADE handle
    # removing child rows in a single statement, instead of SQLAlchemy
    # loading every project (and, transitively, every task) into Python
    # and issuing individual DELETE statements for each one.
    projects = relationship(
        "Project", back_populates="owner",
        cascade="all, delete-orphan", passive_deletes=True,
    )


class Project(Base):
    __tablename__ = "projects"

    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    owner_id    = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at  = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Many projects → one user
    owner = relationship("User", back_populates="projects")
    # One project → many tasks
    tasks = relationship(
        "Task", back_populates="project",
        cascade="all, delete-orphan", passive_deletes=True,
    )


class Task(Base):
    __tablename__ = "tasks"

    id          = Column(Integer, primary_key=True, index=True)
    title       = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    status      = Column(
        String(20),
        nullable=False,
        default="todo",
        server_default="todo",
    )
    priority    = Column(
        String(10),
        nullable=False,
        default="medium",
        server_default="medium",
    )
    due_date    = Column(String(100), nullable=True)   # stored as free-text ("2024-12-31" or "next friday")
    project_id  = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at  = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Many tasks → one project
    project = relationship("Project", back_populates="tasks")

    __table_args__ = (
        CheckConstraint("priority IN ('low','medium','high')", name="ck_task_priority"),
        CheckConstraint("status   IN ('todo','in_progress','done')", name="ck_task_status"),
    )