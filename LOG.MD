mkdir backend && cd backend

uv init --app

uv add fastapi "uvicorn[standard]" pydantic-settings python-dotenv redis asyncpg httpx

uv add "prefect[redis]"

uv add pathway

mkdir -p app/{core,api/v1,models,pipelines,services,utils}

touch app/__init__.py app/main.py app/core/config.py

touch .env.example

cp .env.example .env

uv sync

cd backend

uv sync --group dev

uv run forjd