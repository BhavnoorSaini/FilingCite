"""Create the pgvector extension, tables and indexes. Safe to re-run.

Usage (from backend/):  uv run --env-file ../.env python -m scripts.init_db
"""

import os
from pathlib import Path

import psycopg

SCHEMA = Path(__file__).resolve().parent.parent / "schema.sql"


def main() -> None:
    sql = SCHEMA.read_text().replace("{embedding_dim}", str(int(os.environ["EMBEDDING_DIM"])))
    # Plain psycopg connection: the vector type doesn't exist until this runs.
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        conn.execute(sql)
    print("Schema applied.")


if __name__ == "__main__":
    main()
