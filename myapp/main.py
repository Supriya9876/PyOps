import os
import time
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")

if not all([DB_NAME, DB_USER, DB_PASS]):
    raise RuntimeError("Missing required DB env vars. Did you create a .env / Secret?")

app = FastAPI(title="Task Tracker API")


class Task(BaseModel):
    title: str
    description: str = ""


def get_conn():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS,
        cursor_factory=RealDictCursor,
    )


def init_db(retries: int = 10, delay: int = 3):
    last_err = None
    for _ in range(retries):
        try:
            conn = get_conn()
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS tasks (
                        id SERIAL PRIMARY KEY,
                        title TEXT NOT NULL,
                        description TEXT,
                        completed BOOLEAN NOT NULL DEFAULT FALSE
                    );
                """)
            conn.commit()
            conn.close()
            return
        except Exception as e:
            last_err = e
            time.sleep(delay)
    raise RuntimeError(f"Could not connect to DB after retries: {last_err}")


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/health")
def health():
    try:
        conn = get_conn()
        conn.close()
        return {"status": "ok", "db": "reachable"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"db unreachable: {e}")


@app.post("/tasks")
def create_task(task: Task):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO tasks (title, description) VALUES (%s, %s) RETURNING id, title, description, completed;",
            (task.title, task.description),
        )
        row = cur.fetchone()
    conn.commit()
    conn.close()
    return row


@app.get("/tasks")
def list_tasks():
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT id, title, description, completed FROM tasks ORDER BY id;")
        rows = cur.fetchall()
    conn.close()
    return rows


@app.patch("/tasks/{task_id}/complete")
def complete_task(task_id: int):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE tasks SET completed = TRUE WHERE id = %s RETURNING id, title, description, completed;",
            (task_id,),
        )
        row = cur.fetchone()
    conn.commit()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return row


# @app.delete("/tasks/{task_id}")
# def delete_task(task_id: int):
#     conn = get_conn()
#     with conn.cursor() as cur:
#         cur.execute("DELETE FROM tasks WHERE id = %s RETURNING id;", (task_id,))
#         deleted = cur.fetchone()
#     conn.commit()
#     conn.close()
#     if not deleted:
#         raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
#     return {"message": f"task {task_id} deleted"}