# Backend image for the Interlock console: the FastAPI WebSocket server over the
# SB3 DQN in highway-env, judged by Jev. One session per container, so run one
# always-on instance. The React console is a static Vite build on Vercel that
# points here through VITE_BACKEND_URL.
#
#   docker build --platform linux/amd64 -t interlock-backend .
#   docker run --rm -p 8000:8000 --env-file backend/.env interlock-backend
#   docker run --rm -p 8000:8000 -e JEV_MODE=mock interlock-backend   # offline
#
# The container reads the same variables as `uv run uvicorn backend.server:app`:
# TYPESAFE_API_KEY, JEV_MODE, ESCALATION_TIMEOUT_S, SEED, MODEL_PATH,
# JEV_CACHE_PATH, plus CONSOLE_ORIGINS for the console's origin and PORT.

FROM python:3.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.9.21 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first, so a code change does not re-download torch. The lock pins
# the CPU-only torch wheel on Linux (pyproject.toml, [tool.uv.sources]).
COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# The package, the checkpoint backend.policy loads by default, the eval report
# the metrics tab reads, and the Jev cache when it exists (.dockerignore keeps
# the rest of backend/logs out). A missing checkpoint fails the build here.
COPY backend ./backend
COPY models/dqn_highway.zip ./models/dqn_highway.zip
COPY internal/eval/latest.json ./internal/eval/latest.json
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# highway-env imports pygame; the dummy drivers keep it headless. Run logs and
# cache appends land in the container filesystem and go with it: it is a demo.
ENV SDL_VIDEODRIVER=dummy \
    SDL_AUDIODRIVER=dummy \
    MPLBACKEND=Agg \
    PORT=8000

EXPOSE 8000
CMD ["sh", "-c", "exec uv run --no-sync uvicorn backend.server:app --host 0.0.0.0 --port ${PORT}"]
