# Local development

**First clone?** Use [`START_HERE.md`](START_HERE.md) (`npm run bootstrap` → `dev:api` → `verify`).

## Root scripts

```bash
npm run bootstrap       # once — env, Docker DB, uv sync, deml-ui sync, hooks
npm run doctor          # toolchain + deml-ui.css presence
npm run quality         # catalog + ruff
npm run quality:full    # Also tests + engine fmt/clippy
npm run format          # backend ruff + engine rustfmt
npm run dev:api         # FastAPI → http://127.0.0.1:8000
npm run sync:deml-ui    # Vendor deml-ui CSS into backend/static
npm run verify          # curl /health /ready /capabilities
```

## Backend

```bash
cd backend
uv sync --locked
uv run ruff check . && uv run ruff format --check .
uv run python -m unittest discover -s tests
```

HTML shells (`/`, `/docs`, `/redoc`) load `backend/static/deml-ui.css` + `forjd-backend.css`.

## Engine

```bash
cd engine
cargo fmt --all -- --check
cargo clippy --no-default-features --features server,data-plane -- -D warnings
cargo test --no-default-features --features server,data-plane
```

## Commits

Conventional Commits + squash-merge — [`GIT.md`](GIT.md).

```bash
echo 'feat(api): tighten sealed ingest validation' | python3 scripts/check_commit_msg.py
```
