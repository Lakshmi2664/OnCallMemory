import logging
import asyncio
import concurrent.futures
from typing import List, Dict, Any, Optional
from datetime import datetime
from hindsight_client import Hindsight
from app.config import HINDSIGHT_BASE_URL, HINDSIGHT_API_KEY, HINDSIGHT_BANK_ID

logger = logging.getLogger("oncall_memory.hindsight")

executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)

def _run_in_new_loop(method_name: str, base_url: str, api_key: str, bank_id: str, *args, **kwargs):
    """Creates a new Hindsight client instance inside a dedicated worker loop to prevent aiohttp session reuse errors across loops."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        client = Hindsight(base_url=base_url, api_key=api_key)
        method = getattr(client, method_name)
        return method(bank_id, *args, **kwargs)
    finally:
        loop.close()

class HindsightService:
    def __init__(self, base_url: str = HINDSIGHT_BASE_URL, api_key: str = HINDSIGHT_API_KEY, bank_id: str = HINDSIGHT_BANK_ID):
        self.base_url = base_url
        self.api_key = api_key or "default-key"
        self.bank_id = bank_id

    def _safe_run(self, method_name: str, *args, **kwargs):
        """Runs hindsight client call safely in a separate worker thread with its own event loop."""
        future = executor.submit(
            _run_in_new_loop, method_name, self.base_url, self.api_key, self.bank_id, *args, **kwargs
        )
        return future.result(timeout=10)

    def retain_incident(self, incident: Dict[str, Any]) -> bool:
        """
        Retain a past incident post-mortem in Hindsight.
        client.retain(bank_id, content, context, timestamp)
        """
        try:
            incident_id = incident.get("id", "UNKNOWN")
            service = incident.get("service", "unknown-service")
            symptoms = incident.get("symptoms", "")
            error_log = incident.get("error_log", "")
            metrics = incident.get("metrics", {})
            root_cause = incident.get("root_cause", "")
            fix = incident.get("fix", "")
            time_to_resolve = incident.get("time_to_resolve_mins", 0)

            content = (
                f"Incident ID: {incident_id}\n"
                f"Service: {service}\n"
                f"Symptoms: {symptoms}\n"
                f"Error Log: {error_log}\n"
                f"Metrics: {metrics}\n"
                f"Root Cause: {root_cause}\n"
                f"Fix: {fix}\n"
                f"Time to Resolve: {time_to_resolve} minutes"
            )
            context = f"Post-mortem for incident {incident_id} in service {service}"

            ts_str = incident.get("timestamp")
            timestamp = None
            if ts_str:
                try:
                    timestamp = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                except Exception:
                    timestamp = None

            logger.info(f"Retaining incident {incident_id} into Hindsight bank '{self.bank_id}'")
            self._safe_run(
                "retain",
                content=content,
                context=context,
                timestamp=timestamp
            )
            return True
        except Exception as e:
            logger.error(f"Failed to retain incident in Hindsight: {str(e)}")
            return False

    def retain_feedback(self, incident_id: str, suggestion: str, worked: bool, notes: Optional[str] = None) -> bool:
        """
        Retain feedback outcome in Hindsight so future suggestions favor fixes that worked.
        """
        try:
            status = "SUCCESSFUL / WORKED" if worked else "FAILED / DID NOT WORK"
            content = (
                f"Feedback for Incident: {incident_id}\n"
                f"Suggested Fix: {suggestion}\n"
                f"Outcome: {status}\n"
                f"Notes: {notes or 'None'}"
            )
            context = f"Feedback outcome record for incident response resolution"

            logger.info(f"Retaining feedback for incident {incident_id} in Hindsight bank '{self.bank_id}'")
            self._safe_run(
                "retain",
                content=content,
                context=context,
                timestamp=datetime.utcnow()
            )
            return True
        except Exception as e:
            logger.error(f"Failed to retain feedback in Hindsight: {str(e)}")
            return False

    def recall_memories(self, query: str) -> List[Dict[str, Any]]:
        """
        Recall past incidents and post-mortems matching the query.
        client.recall(bank_id, query)
        """
        try:
            logger.info(f"Recalling memories for query from Hindsight bank '{self.bank_id}'")
            response = self._safe_run(
                "recall",
                query=query
            )
            recalled_list = []
            results = getattr(response, "results", []) or getattr(response, "memories", []) or []

            if not results and hasattr(response, "__iter__"):
                try:
                    results = list(response)
                except Exception:
                    pass

            for item in results:
                if isinstance(item, dict):
                    recalled_list.append({
                        "content": item.get("content") or item.get("text") or str(item),
                        "score": item.get("score") or item.get("relevance", 1.0),
                        "context": item.get("context", "")
                    })
                else:
                    content = getattr(item, "content", None) or getattr(item, "text", None) or str(item)
                    score = getattr(item, "score", 1.0)
                    context = getattr(item, "context", "")
                    recalled_list.append({
                        "content": content,
                        "score": score,
                        "context": context
                    })

            return recalled_list
        except Exception as e:
            logger.error(f"Failed to recall memories from Hindsight: {str(e)}")
            return []

    def reflect_patterns(self, query: str = "what patterns keep recurring across our incidents?") -> str:
        """
        Reflect on bank memories to identify recurring patterns.
        client.reflect(bank_id, query)
        """
        try:
            logger.info(f"Reflecting on patterns in Hindsight bank '{self.bank_id}'")
            response = self._safe_run(
                "reflect",
                query=query
            )
            if hasattr(response, "text") and response.text:
                return response.text
            if hasattr(response, "summary") and response.summary:
                return response.summary
            if hasattr(response, "content") and response.content:
                return response.content
            return str(response)
        except Exception as e:
            logger.error(f"Failed to reflect patterns from Hindsight: {str(e)}")
            return f"Unable to fetch pattern reflection from Hindsight: {str(e)}"

# Singleton instance
hindsight_service = HindsightService()
