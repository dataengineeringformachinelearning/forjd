"""CLI entry: `uv run forjd` — uvicorn with scoped reload for reliable DX."""

import uvicorn

from app.core.config import settings


def main() -> None:
    # --- Dev reload (scoped to app/) ---
    # Avoid watching .venv / engine rebuild trees (maturin) which thrash HMR.
    reload = bool(settings.DEBUG)
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=reload,
        reload_dirs=["app"] if reload else None,
        reload_excludes=["*.pyc", "__pycache__"] if reload else None,
    )


if __name__ == "__main__":
    main()
