import os
from pathlib import Path

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    WTF_CSRF_TIME_LIMIT = 3600
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
    DATABASE_PATH = os.environ.get("DATABASE_PATH", "./data/retention.db")
    LOG_PATH = os.environ.get("LOG_PATH", "./logs/retention.log")
    WORKER_POLL_SECONDS = int(os.environ.get("WORKER_POLL_SECONDS", "5"))
    MAX_CONTENT_LENGTH = 1024 * 1024
