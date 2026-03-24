# BriefBox Dev Setup

## Local Requirements

- Python 3.13+
- `uv`
- Ollama installed locally
- A local Ollama model available for later milestones

## Install And Sync

```bash
UV_CACHE_DIR=.cache/uv uv sync --extra dev
```

## Run The API

```bash
UV_CACHE_DIR=.cache/uv uv run uvicorn briefbox.app.api:app --reload
```

API health check:

```bash
curl http://127.0.0.1:8000/health
```

## Run The Chainlit UI

```bash
UV_CACHE_DIR=.cache/uv uv run chainlit run briefbox/chainlit_app.py
```

## Run Tests

```bash
UV_CACHE_DIR=.cache/uv uv run --extra dev pytest
```

## Run Lint

```bash
UV_CACHE_DIR=.cache/uv uv run --extra dev ruff check .
UV_CACHE_DIR=.cache/uv uv run --extra dev ruff format --check .
```

## Task Shortcuts

```bash
task sync
task api
task ui
task test
task lint
task check
```
