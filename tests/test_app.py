import json
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200

@patch("app.main.hindsight_service.retain_incident")
def test_seed_endpoint(mock_retain):
    mock_retain.return_value = True
    response = client.post("/seed")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["incidents_loaded"] == 15
    assert mock_retain.call_count == 15

@patch("app.main.hindsight_service.recall_memories")
@patch("app.main.call_llm_with_retry")
def test_incident_endpoint_with_memory(mock_llm, mock_recall):
    mock_recall.return_value = [
        {"content": "Past Incident INC-1001: Connection pool timeout", "score": 0.95, "context": "post-mortem"}
    ]
    mock_llm.return_value = json.dumps({
        "diagnosis": "Database connection pool exhaustion detected based on past INC-1001 memory.",
        "suggested_steps": ["Increase statement_timeout", "Check pool size"]
    })

    payload = {
        "alert_text": "sqlalchemy.exc.TimeoutError: QueuePool limit of size 20 overflow 10 reached",
        "memory": True
    }
    response = client.post("/incident", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "Database connection pool" in data["diagnosis"]
    assert len(data["suggested_steps"]) == 2
    assert len(data["recalled_memories"]) == 1
    assert mock_recall.called

@patch("app.main.hindsight_service.recall_memories")
@patch("app.main.call_llm_with_retry")
def test_incident_endpoint_without_memory(mock_llm, mock_recall):
    mock_llm.return_value = json.dumps({
        "diagnosis": "Generic connection error without memory context.",
        "suggested_steps": ["Check database service"]
    })

    payload = {
        "alert_text": "sqlalchemy.exc.TimeoutError: QueuePool limit of size 20 overflow 10 reached",
        "memory": False
    }
    response = client.post("/incident", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "Generic connection error" in data["diagnosis"]
    assert len(data["recalled_memories"]) == 0
    assert not mock_recall.called

@patch("app.main.hindsight_service.retain_feedback")
def test_feedback_endpoint(mock_retain_fb):
    mock_retain_fb.return_value = True
    payload = {
        "incident_id": "INC-1001",
        "suggestion": "Increased statement_timeout=5000ms",
        "worked": True,
        "notes": "Resolved DB pool starvation in checkout service"
    }
    response = client.post("/feedback", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert mock_retain_fb.called

@patch("app.main.hindsight_service.reflect_patterns")
def test_patterns_endpoint(mock_reflect):
    mock_reflect.return_value = "Recurring pattern: Database pool exhaustions across checkout, profile, and billing services."
    response = client.get("/patterns")
    assert response.status_code == 200
    data = response.json()
    assert "Recurring pattern" in data["reflection"]
    assert mock_reflect.called
