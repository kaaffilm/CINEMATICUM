from __future__ import annotations

import sqlite3
from pathlib import Path


DB_PATH = Path(".cinematicum_media/cinematicum.db")


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS film_cases (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'DEVELOPMENT'
);

CREATE TABLE IF NOT EXISTS scenes (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL,
  title TEXT NOT NULL,
  scene_order INTEGER NOT NULL,
  dramatic_function TEXT NOT NULL,
  FOREIGN KEY(case_id) REFERENCES film_cases(id)
);

CREATE TABLE IF NOT EXISTS shots (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL,
  scene_id TEXT NOT NULL,
  shot_order INTEGER NOT NULL,
  duration INTEGER NOT NULL,
  prompt TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'PLANNED',
  FOREIGN KEY(case_id) REFERENCES film_cases(id),
  FOREIGN KEY(scene_id) REFERENCES scenes(id)
);

CREATE TABLE IF NOT EXISTS generation_jobs (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL,
  shot_id TEXT NOT NULL,
  backend TEXT NOT NULL,
  model TEXT,
  status TEXT NOT NULL DEFAULT 'QUEUED',
  prompt TEXT NOT NULL,
  seed INTEGER,
  FOREIGN KEY(case_id) REFERENCES film_cases(id),
  FOREIGN KEY(shot_id) REFERENCES shots(id)
);

CREATE TABLE IF NOT EXISTS takes (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL,
  shot_id TEXT NOT NULL,
  job_id TEXT,
  backend TEXT NOT NULL,
  model TEXT,
  prompt TEXT NOT NULL,
  seed INTEGER,
  file_path TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  duration INTEGER,
  width INTEGER,
  height INTEGER,
  fps INTEGER,
  status TEXT NOT NULL DEFAULT 'GENERATED',
  FOREIGN KEY(case_id) REFERENCES film_cases(id),
  FOREIGN KEY(shot_id) REFERENCES shots(id),
  FOREIGN KEY(job_id) REFERENCES generation_jobs(id)
);

CREATE TABLE IF NOT EXISTS selected_takes (
  shot_id TEXT PRIMARY KEY,
  take_id TEXT NOT NULL,
  case_id TEXT NOT NULL,
  FOREIGN KEY(take_id) REFERENCES takes(id),
  FOREIGN KEY(case_id) REFERENCES film_cases(id)
);

CREATE TABLE IF NOT EXISTS final_masters (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL,
  version TEXT NOT NULL,
  file_path TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  runtime_seconds INTEGER,
  status TEXT NOT NULL DEFAULT 'MASTER_RENDERED',
  FOREIGN KEY(case_id) REFERENCES film_cases(id)
);
"""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> Path:
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
    return DB_PATH
