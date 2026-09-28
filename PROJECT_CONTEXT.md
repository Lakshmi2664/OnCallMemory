# PROJECT_CONTEXT.md

## Project Overview
**OnCallMemory** is an incident-response AI agent using **Hindsight** for persistent memory and **Groq** (with OpenAI API compatibility) for LLM inferences.

## Core Features
1. **Persistent Incident Memory**: Retain and recall past incident post-mortems and feedback outcomes using Hindsight memory banks (`bank_id`, e.g., `acme-platform-team`).
2. **Context-Aware Diagnosis**: Evaluate incoming alerts with or without Hindsight recalled memories, demonstrating how past learnings improve diagnosis quality and actionable steps.
3. **Feedback Loop**: Capture on-call engineer feedback (`worked: bool`, `notes`, `suggestion`) to refine future suggestions.
4. **Pattern Recognition**: Identify recurring incident patterns across systems using `client.reflect()`.
5. **Interactive UI**: Single-page frontend featuring alert input, Memory ON/OFF toggle, side-by-side comparison mode (OFF vs ON), recalled incident drawer, feedback form, and pattern insight display.

## Repository Structure & Modules
- `data/incidents.json`: 15 realistic incident records including stack traces, metrics, root causes, fixes, and resolution times. Includes 3 incidents sharing a common root cause (Database Connection Pool Exhaustion) with varied phrasing.
- `app/config.py`: Environment variable configuration (`HINDSIGHT_BASE_URL`, `HINDSIGHT_API_KEY`, `GROQ_API_KEY`, `HINDSIGHT_BANK_ID`).
- `app/llm.py`: Groq LLM API wrapper using `openai` Python SDK (`openai/gpt-oss-120b` fallback `qwen/qwen3-32b`) with retries, structured JSON parsing, and graceful error handling.
- `app/hindsight_service.py`: Hindsight client wrapper handling `client.retain`, `client.recall`, and `client.reflect` calls for bank `acme-platform-team`.
- `app/main.py`: FastAPI application serving REST endpoints (`POST /seed`, `POST /incident`, `POST /feedback`, `GET /patterns`, `GET /`) and static frontend files.
- `app/static/index.html`: Modern, responsive single-page HTML/JS frontend styled with Bootstrap 5.
- `tests/test_llm.py`: Unit tests for LLM client parsing, prompt building, and fallback behavior.
- `tests/test_api.py`: Integration tests for FastAPI endpoints.
- `README.md`: Project documentation including Mermaid architecture diagram and detailed 'How Hindsight memory is used' section.

## Verification & Status
- Unit and integration tests in `tests/test_llm.py` and `tests/test_api.py` run and pass cleanly.
- Frontend rendering verified via Playwright headless screenshot testing.
