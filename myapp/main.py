import os
import time
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")   # safe to default — not a secret
DB_PORT = os.getenv("DB_PORT", "5432")        # safe to default — not a secret
DB_NAME = os.getenv("DB_NAME")                # no default — must come from .env
DB_USER = os.getenv("DB_USER")                # no default — must come from .env
DB_PASS = os.getenv("DB_PASS")                # no default — must come from .env

app = FastAPI(title="Minimal Infra Demo API")


class Item(BaseModel):
    name: str
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
                    CREATE TABLE IF NOT EXISTS items (
                        id SERIAL PRIMARY KEY,
                        name TEXT NOT NULL,
                        description TEXT
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


@app.post("/items")
def create_item(item: Item):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO items (name, description) VALUES (%s, %s) RETURNING id, name, description;",
            (item.name, item.description),
        )
        row = cur.fetchone()
    conn.commit()
    conn.close()
    return row


@app.get("/items")
def list_items():
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT id, name, description FROM items ORDER BY id;")
        rows = cur.fetchall()
    conn.close()
    return rows

#@app.delete("/items/{item_id}")
# def delete_item(item_id: int):
#     conn = get_conn()
#     with conn.cursor() as cur:
#         cur.execute("DELETE FROM items WHERE id = %s RETURNING id;", (item_id,))
#         deleted = cur.fetchone()
#     conn.commit()
#     conn.close()
#     if not deleted:
#         raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
#     return {"message": f"item {item_id} deleted"}