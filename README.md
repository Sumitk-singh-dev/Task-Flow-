# Task-Flow-
Full-stack task manager (FastAPI + vanilla JS) with a quick-add feature that parses title, priority, and due date from plain text.

AI-assisted task management platform built with **FastAPI**, **SQLAlchemy**, and a vanilla JS frontend.

---

## Features

- Full CRUD for users, projects, and tasks
- Dashboard with per-project statistics and progress bars
- Task filtering by project, status, and priority
- Live task search (title + description) with keyword highlighting
- Sort tasks by title, priority, status, due date, or creation order
- **Quick Add Task** — create a task from a single free-text sentence

---

## Quick Start

git clone https://github.com/Sumitk-singh-dev/Task-Flow-.git
cd Task-Flow-

install python version 3.11
# Create a fresh venv
python -3.11 -m venv venv

# Activate it — command depends on their shell:
venv\Scripts\activate          # Windows PowerShell / CMD
source venv/Scripts/activate   # Windows Git Bash
source venv/bin/activate       # macOS/Linux

# Install dependencies
pip install -r requirements.txt


# Create a `.env` file and add your PostgreSQL connection string:
DATABASE_URL=your_postgresql_connection_string

# 4. Start the server
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload

# 5. Open the frontend
# Open frontend/index.html in your browser (or use VS Code Live Server)
```

Visit `http://127.0.0.1:8000/health` to confirm the API is running.

---

## Quick Add Task Feature

### Endpoint

```
POST /tasks/quick-add
```

**Request body:**

```json
{
  "description": "Finish the report next Friday, it's urgent",
  "project_id": 1
}
```

**Response (201):** the created task object — identical to the response from `POST /tasks`.

---

## Prompting Technique

### Approach: Zero-Shot

This implementation is primarily **zero-shot**. The system instruction defines the complete expected parsing behavior — extracting title, priority, and due-date hint from a free-text sentence — without providing worked examples inside the prompt itself.

```python
messages = [
    {
        "role": "system",
        "content": (
            "Parse the task description and return title, priority, "
            "and due_date_hint according to the required rules."
        )
    },
    {
        "role": "user",
        "content": description
    }
]
```

**Why zero-shot is suitable here:**

The parsing rules are fully enumerable and deterministic (keyword lists, priority order, removal rules). A language model following the system instruction can apply these rules without needing demonstration examples. This keeps the prompt concise and the token cost minimal compared to few-shot prompting, which embeds multiple input/output examples in every API call.

**How deterministic mock rules improve reliability:**

In production the default parser is a pure Python function — no network call, no API key, no latency, no cost, and 100% reproducible output. This eliminates the non-determinism and failure modes of a live LLM while preserving the exact same interface.

**Why this structure supports a real LLM later:**

The `parse_task_description()` function is the single entry point. Switching to a real language model requires only adding an implementation behind the `USE_REAL_LLM=true` environment flag. The endpoint, validation, and database logic are completely unchanged. The role-based message structure is already in place, so the real LLM call slots in without architectural changes.

---

## Parsed Examples

Each example shows the input description and the exact JSON the parser produces.

### Example 1 — High priority, no date

```
Input:  "This is urgent, mark it ASAP please"
```

```json
{
  "title": "This is , mark it please",
  "priority": "high",
  "due_date_hint": null
}
```

Both `urgent` and `ASAP` are removed. High priority wins.

---

### Example 2 — Whitespace-only input

```
Input:  "   "
```

```json
{
  "title": "Untitled task",
  "priority": "medium",
  "due_date_hint": null
}
```

When the cleaned title is empty, `"Untitled task"` is used.

---

### Example 3 — High priority + next weekday date

```
Input:  "Finish the report next Friday, it's urgent"
```

```json
{
  "title": "Finish the report , it's",
  "priority": "high",
  "due_date_hint": "next friday"
}
```

`next friday` is detected first (before bare `friday`). `urgent` is removed from the title.

---

### Example 4 — Multiple date occurrences removed

```
Input:  "tomorrow review tomorrow"
```

```json
{
  "title": "review",
  "priority": "medium",
  "due_date_hint": "tomorrow"
}
```

All occurrences of the matched date phrase are removed from the title.

---

### Example 5 — Low priority + today

```
Input:  "Update the wiki today, low priority"
```

```json
{
  "title": "Update the wiki , ",
  "priority": "low",
  "due_date_hint": "today"
}
```

`low priority` is removed. `today` is detected and removed from the title.

---

### Example 6 — Bare weekday, medium priority

```
Input:  "Call the client on Monday"
```

```json
{
  "title": "Call the client on ",
  "priority": "medium",
  "due_date_hint": "monday"
}
```

No priority keyword — defaults to medium. `monday` is the first matching date phrase.

---

### Example 7 — High+low keywords, next week

```
Input:  "Do this urgent whenever, next week"
```

```json
{
  "title": "Do this  , ",
  "priority": "high",
  "due_date_hint": "next week"
}
```

Both `urgent` and `whenever` are removed from the title. High wins over low.

---

## Running Tests

```bash
cd backend
python -m pytest tests/ -v
```

Tests use an in-memory SQLite database — no Postgres or network connection required.

---

## Environment Variables

| Variable        | Default | Description                                      |
|-----------------|---------|--------------------------------------------------|
| `DATABASE_URL`  | —       | PostgreSQL connection string (required)          |
| `USE_REAL_LLM`  | `false` | Set to `true` to use a real LLM parser           |
| `OPENAI_API_KEY`| —       | Required only when `USE_REAL_LLM=true`           |

---

## API Reference

| Method | Path                  | Description                          |
|--------|-----------------------|--------------------------------------|
| GET    | /health               | Liveness check                       |
| POST   | /users                | Create user                          |
| GET    | /users                | List users                           |
| GET    | /users/{id}           | Get user                             |
| DELETE | /users/{id}           | Delete user                          |
| POST   | /projects             | Create project                       |
| GET    | /projects             | List projects                        |
| GET    | /projects/{id}        | Get project                          |
| DELETE | /projects/{id}        | Delete project                       |
| POST   | /tasks                | Create task (manual)                 |
| GET    | /tasks                | List tasks                           |
| **POST** | **/tasks/quick-add** | **Create task from free text**      |
| GET    | /tasks/{id}           | Get task                             |
| PUT    | /tasks/{id}           | Update task                          |
| DELETE | /tasks/{id}           | Delete task                          |
| GET    | /stats                | Per-project task statistics          |
| GET    | /stats/{id}           | Stats for one project                |
