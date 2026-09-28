# OnCallMemory - Project Context

## Overview
OnCallMemory is an intelligent incident-response AI agent powered by Hindsight persistent memory and LLMs (via Groq API using OpenAI-compatible client). It assists SREs and on-call engineers in diagnosing production incidents, recalling relevant past incidents and resolution outcomes, and learning from feedback.

## Architecture
- **Backend**: FastAPI (Python 3.12)
- **Memory Service**: Hindsight (`hindsight-client`)
- **LLM Provider**: Groq OpenAI-compatible endpoint (`https://api.groq.com/openai/v1`)
  - Primary model: `openai/gpt-oss-120b`
  - Fallback model: `qwen/qwen3-32b`
- **Frontend**: Single-Page HTML5 / Vanilla JS + Tailwind CSS with side-by-side compare mode.

## Key Configuration Variables (.env)
- `HINDSIGHT_BASE_URL`
- `HINDSIGHT_API_KEY`
- `GROQ_API_KEY`
- `HINDSIGHT_BANK_ID` (Default: `acme-platform-team`)

## Current Progress Status
- [x] Initialized `PROJECT_CONTEXT.md` and `.gitignore`
- [x] Created seed dataset (`data/incidents.json`) with 15 realistic incidents
- [x] Backend setup and LLM retry/fallback logic (`app/config.py`, `app/llm.py`)
- [x] Hindsight service wrapper (`app/hindsight_services.py`)
- [x] FastAPI endpoints (`app/main.py`)
- [x] Frontend interface (`static/index.html`)
- [x] Documentation (`README.md`)
- [x] Test suite execution (`tests/test_app.py`) - All 6 pytest test cases passing.
