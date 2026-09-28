import json
import pytest
from unittest.mock import MagicMock, patch
from app.llm import LLMClient


def test_llm_build_prompt():
    client = LLMClient(api_key="test_key")
    prompt_no_mem = client._build_prompt("Database timeout error", None)
    assert "Database timeout error" in prompt_no_mem
    assert "NOTE: Hindsight memory is DISABLED" in prompt_no_mem

    memories = [{"content": "Past incident: Hikari pool exhausted", "context": "auth-service"}]
    prompt_mem = client._build_prompt("Database timeout error", memories)
    assert "Past incident: Hikari pool exhausted" in prompt_mem


def test_llm_parse_json_response():
    client = LLMClient(api_key="test_key")
    json_text = '```json\n{"diagnosis": "Pool exhausted", "suggested_steps": ["Step 1", "Step 2"]}\n```'
    parsed = client._parse_json_response(json_text)
    assert parsed is not None
    assert parsed["diagnosis"] == "Pool exhausted"
    assert len(parsed["suggested_steps"]) == 2


def test_llm_fallback_response():
    client = LLMClient(api_key="test_key")
    memories = [{"content": "Hikari connection pool leak in OAuth token generation"}]
    res = client._fallback_response("DB alert", memories)
    assert "Database Connection Pool Exhaustion" in res["diagnosis"]
    assert len(res["suggested_steps"]) > 0


@patch("app.llm.GROQ_API_KEY", "gsk_valid_mock_key_for_test")
@patch("app.llm.OpenAI")
def test_llm_diagnose_success(mock_openai_class):
    mock_openai_instance = MagicMock()
    mock_openai_class.return_value = mock_openai_instance

    mock_completion = MagicMock()
    mock_completion.choices = [
        MagicMock(message=MagicMock(content='{"diagnosis": "LLM diagnosed issue", "suggested_steps": ["Fix it"]}'))
    ]
    mock_openai_instance.chat.completions.create.return_value = mock_completion

    client = LLMClient(api_key="gsk_valid_mock_key_for_test")
    result = client.diagnose_incident("Alert high CPU")
    assert result["diagnosis"] == "LLM diagnosed issue"
    assert result["suggested_steps"] == ["Fix it"]


@patch("app.llm.GROQ_API_KEY", "gsk_valid_mock_key_for_test")
@patch("app.llm.OpenAI")
def test_llm_diagnose_fallback_on_error(mock_openai_class):
    mock_openai_instance = MagicMock()
    mock_openai_class.return_value = mock_openai_instance
    mock_openai_instance.chat.completions.create.side_effect = Exception("API connection error")

    client = LLMClient(api_key="gsk_valid_mock_key_for_test")
    result = client.diagnose_incident("Alert high CPU", max_retries=1)
    assert "suggested_steps" in result
    assert len(result["suggested_steps"]) > 0
