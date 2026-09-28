import datetime
import json
import os
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.config import HINDSIGHT_BANK_ID
from app.hindsight_service import HindsightService
from app.llm import LLMClient

app = FastAPI(title="OnCallMemory API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

hindsight_svc = HindsightService()
llm_client = LLMClient()


class IncidentRequest(BaseModel):
    alert_text: str = Field(..., description="The system alert, error log, or symptom description.")
    memory: bool = Field(True, description="Whether to recall past memories from Hindsight.")


class FeedbackRequest(BaseModel):
    incident_id: str = Field(..., description="Identifier for the incident.")
    suggestion: str = Field(..., description="The suggestion or step that was attempted.")
    worked: bool = Field(..., description="Whether the suggestion resolved the issue.")
    notes: Optional[str] = Field("", description="Additional notes or comments on the resolution.")


@app.post("/seed")
def seed_incidents(data_path: str = "data/incidents.json"):
    """
    Seed Hindsight memory with past incidents and post-mortems from data/incidents.json.
    """
    if not os.path.exists(data_path):
        raise HTTPException(status_code=404, detail=f"Seed data file not found at {data_path}")

    try:
        with open(data_path, "r", encoding="utf-8") as f:
            incidents = json.load(f)

        seeded_count = 0
        for inc in incidents:
            content = (
                f"Incident {inc.get('id', 'N/A')} [{inc.get('service', 'unknown-service')}]: "
                f"Symptoms: {inc.get('symptoms', '')}. "
                f"Error Log: {inc.get('error_log', '')}. "
                f"Metrics: {inc.get('metrics', '')}. "
                f"Root Cause: {inc.get('root_cause', '')}. "
                f"Fix: {inc.get('fix', '')}. "
                f"Time to resolve: {inc.get('time_to_resolve_minutes', 'N/A')} minutes."
            )
            context = f"Service: {inc.get('service', '')} | ID: {inc.get('id', '')}"
            ts_str = inc.get("timestamp")
            timestamp = None
            if ts_str:
                try:
                    timestamp = datetime.datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                except Exception:
                    timestamp = None

            hindsight_svc.retain(content=content, context=context, timestamp=timestamp)
            seeded_count += 1

        return {
            "status": "success",
            "message": f"Successfully seeded {seeded_count} incidents into Hindsight memory bank '{HINDSIGHT_BANK_ID}'.",
            "count": seeded_count,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to seed memory: {str(e)}")


@app.post("/incident")
def diagnose_incident(req: IncidentRequest):
    """
    Diagnose a new alert.
    If memory=True, recall similar past incidents and pass them to LLM.
    If memory=False, pass alert directly to LLM without memory context.
    """
    recalled_memories: List[Dict[str, Any]] = []

    if req.memory:
        recalled_memories = hindsight_svc.recall(query=req.alert_text)

    llm_result = llm_client.diagnose_incident(alert_text=req.alert_text, memories=recalled_memories if req.memory else None)

    return {
        "diagnosis": llm_result.get("diagnosis", ""),
        "suggested_steps": llm_result.get("suggested_steps", []),
        "recalled_memories": recalled_memories,
    }


@app.post("/feedback")
def submit_feedback(req: FeedbackRequest):
    """
    Retain feedback outcome so future suggestions favor fixes that worked.
    """
    outcome = "SUCCESS (Worked)" if req.worked else "FAILURE (Did Not Work)"
    content = (
        f"Feedback for Incident {req.incident_id}: "
        f"Suggestion '{req.suggestion}' was attempted. Outcome: {outcome}. "
        f"Notes: {req.notes or 'None'}"
    )
    context = f"Incident ID: {req.incident_id} | Outcome: {outcome}"

    hindsight_svc.retain(content=content, context=context)

    return {
        "status": "success",
        "message": f"Feedback retained for incident {req.incident_id}. Outcome recorded as {outcome}.",
    }


@app.get("/patterns")
def get_patterns(query: str = "what patterns keep recurring across our incidents?"):
    """
    Reflect on recurring patterns across past incidents.
    """
    return hindsight_svc.reflect(query=query)


# Mount static directory and serve index.html
os.makedirs("app/static", exist_ok=True)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/")
def read_root():
    index_path = os.path.join("app", "static", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "OnCallMemory Backend API is running. Add index.html to app/static."}
