"""Repo-relative paths shared by the backend modules."""

from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
REPO_DIR = BACKEND_DIR.parent
MODELS_DIR = REPO_DIR / "models"
LOGS_DIR = BACKEND_DIR / "logs"
INTERNAL_DIR = REPO_DIR / "internal"

DEFAULT_MODEL_PATH = MODELS_DIR / "dqn_highway.zip"
ENV_FILE = BACKEND_DIR / ".env"
