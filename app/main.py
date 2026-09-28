import json
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.hindsight_services import hindsight_service
from app.llm import call_llm_with_retry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("oncall_memory.main")

app = FastAPI(
    title="OnCallMemory API",
    description="Incident-response AI agent using Hindsight persistent memory and Groq LLM",
    version="1.0.0"
)

# Models
class IncidentRequest(BaseModel):
    alert_text: str = Field(..., description="Alert payload or description of the ongoing incident")
    memory: bool = Field(True, description="Enable or disable Hindsight past incident retrieval")

class FeedbackRequest(BaseModel):
    incident_id: str = Field(..., description="ID or title of the incident being resolved")
    suggestion: str = Field(..., description="The suggested resolution step that was applied")
    worked: bool = Field(..., description="Whether the suggestion resolved the issue")
    notes: Optional[str] = Field(None, description="Additional post-mortem notes or comments")

class IncidentResponse(BaseModel):
    diagnosis: str
    suggested_steps: List[str]
    recalled_memories: List[Dict[str, Any]] = []

class SeedResponse(BaseModel):
    status: str
    incidents_loaded: int
    message: str

class PatternsResponse(BaseModel):
    reflection: str

@app.post("/seed", response_model=SeedResponse)
def seed_incidents():
    """
    POST /seed: Load data/incidents.json into Hindsight via retain.
    """
    file_path = Path("data/incidents.json")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="data/incidents.json file not found")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            incidents = json.load(f)

        success_count = 0
        for incident in incidents:
            res = hindsight_service.retain_incident(incident)
            if res:
                success_count += 1

        return SeedResponse(
            status="success",
            incidents_loaded=success_count,
            message=f"Successfully retained {success_count} / {len(incidents)} incidents into Hindsight bank '{hindsight_service.bank_id}'"
        )
    except Exception as e:
        logger.error(f"Error seeding data: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to seed incidents: {str(e)}")

@app.post("/incident", response_model=IncidentResponse)
def analyze_incident(req: IncidentRequest):
    """
    POST /incident {alert_text, memory: bool}:
    If memory=true, recall similar past incidents and pass them to the LLM.
    If false, LLM only.
    Return {diagnosis, suggested_steps, recalled_memories}.
    """
    recalled_memories = []
    if req.memory:
        recalled_memories = hindsight_service.recall_memories(req.alert_text)

    # Build prompt for LLM
    system_prompt = (
        "You are OnCallMemory, an expert Site Reliability Engineer (SRE) assistant. "
        "Analyze production alerts, identify potential root causes, and provide clear, actionable remediation steps. "
        "Respond ONLY in valid JSON format with keys: \"diagnosis\" (string) and \"suggested_steps\" (array of strings)."
    )

    user_content = f"Incoming Alert/Incident:\n{req.alert_text}\n"

    if req.memory and recalled_memories:
        user_content += "\nRECALLED PAST INCIDENTS & FEEDBACK (Hindsight Memory):\n"
        for idx, mem in enumerate(recalled_memories, start=1):
            user_content += f"Memory #{idx} (Relevance Score: {mem.get('score', 'N/A')}):\n{mem.get('content')}\n---\n"
    elif req.memory:
        user_content += "\n(No previous matching memories found in Hindsight bank)\n"
    else:
        user_content += "\n(Note: Persistent memory is DISABLED for this diagnosis)\n"

    user_content += (
        "\nProvide diagnosis and step-by-step remediation suggestions based on the alert and recalled post-mortems if available.\n"
        "Output pure JSON with structure: {\"diagnosis\": \"...\", \"suggested_steps\": [\"...\"]}"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

    llm_output = call_llm_with_retry(messages)

    # Parse LLM response
    diagnosis = "Diagnosis generated based on alert symptoms."
    suggested_steps = []

    try:
        # Clean JSON markdown fences if present
        clean_text = llm_output.strip()
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]
        if clean_text.startswith("```"):
            clean_text = clean_text[3:]
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]
        clean_text = clean_text.strip()

        parsed = json.loads(clean_text)
        diagnosis = parsed.get("diagnosis", diagnosis)
        suggested_steps = parsed.get("suggested_steps", [])
    except Exception as e:
        logger.warning(f"Could not parse LLM response as JSON: {e}. Output was: {llm_output}")
        diagnosis = llm_output
        suggested_steps = [
            "Check service health and metrics",
            "Review recent deployments and config changes",
            "Examine application logs for stack traces"
        ]

    return IncidentResponse(
        diagnosis=diagnosis,
        suggested_steps=suggested_steps,
        recalled_memories=recalled_memories
    )

@app.post("/feedback")
def submit_feedback(req: FeedbackRequest):
    """
    POST /feedback {incident_id, suggestion, worked: bool, notes}:
    Retain the outcome so future suggestions favor fixes that worked.
    """
    success = hindsight_service.retain_feedback(
        incident_id=req.incident_id,
        suggestion=req.suggestion,
        worked=req.worked,
        notes=req.notes
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to retain feedback in Hindsight")
    return {"status": "success", "message": "Feedback recorded successfully in Hindsight memory bank"}

@app.get("/patterns", response_model=PatternsResponse)
def get_patterns():
    """
    GET /patterns: reflect summary.
    """
    reflection = hindsight_service.reflect_patterns("what patterns keep recurring across our incidents?")
    return PatternsResponse(reflection=reflection)

# Mount static frontend directory
static_dir = Path("static")
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def read_root():
    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "OnCallMemory API running. Frontend static/index.html ready."}
