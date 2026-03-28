# BriefBox Dev Setup

## Local Requirements

- Python 3.13.x
- `uv`
- Ollama installed locally
- A local Ollama model available for later milestones

Recommended local model:

```bash
ollama pull qwen3.5:0.8b
```

If you want to use a different local model, set `BRIEFBOX_OLLAMA_MODEL`.

## Install And Sync

```bash
uv venv --python 3.13.9
uv sync --group dev
```

## Run The API

```bash
uv run uvicorn briefbox.app.api:app --reload
```

API health check:

```bash
curl http://127.0.0.1:8000/health
```

## Run The Chainlit UI

```bash
uv run chainlit run briefbox/chainlit_app.py --port 8001
```

The local setup uses two processes:

- FastAPI backend on `http://127.0.0.1:8000`
- Chainlit UI on `http://127.0.0.1:8001`

## Run Tests

```bash
uv run --extra dev pytest
```

## Run Lint

```bash
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
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
