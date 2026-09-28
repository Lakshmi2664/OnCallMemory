import json
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_seed_endpoint():
    response = client.post("/seed")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["count"] == 15


def test_incident_endpoint_memory_true():
    # Seed first
    client.post("/seed")

    payload = {
        "alert_text": "FATAL: remaining connection slots are reserved for non-replication superuser connections HikariCP",
        "memory": True
    }
    response = client.post("/incident", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "diagnosis" in data
    assert "suggested_steps" in data
    assert "recalled_memories" in data
    assert isinstance(data["suggested_steps"], list)
    assert len(data["recalled_memories"]) > 0


def test_incident_endpoint_memory_false():
    payload = {
        "alert_text": "HTTP 500 internal server error",
        "memory": False
    }
    response = client.post("/incident", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "diagnosis" in data
    assert "suggested_steps" in data
    assert len(data["recalled_memories"]) == 0


def test_feedback_endpoint():
    payload = {
        "incident_id": "INC-1001",
        "suggestion": "Increased maxHikariPoolSize to 100",
        "worked": True,
        "notes": "Resolved connection starvation immediately"
    }
    response = client.post("/feedback", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"


def test_patterns_endpoint():
    response = client.get("/patterns")
    assert response.status_code == 200
    data = response.json()
    assert "patterns_summary" in data
    assert "query" in data
