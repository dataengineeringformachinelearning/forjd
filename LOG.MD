mkdir backend && cd backend

uv init --app

uv add fastapi "uvicorn[standard]" pydantic-settings python-dotenv redis asyncpg httpx

uv add "prefect[redis]"

uv add pathway