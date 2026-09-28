import json
import logging
import time
from typing import Any, Dict, List, Optional
from openai import OpenAI
from app.config import GROQ_API_KEY, GROQ_BASE_URL, PRIMARY_MODEL, FALLBACK_MODEL

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or GROQ_API_KEY or "dummy_key"
        self.base_url = base_url or GROQ_BASE_URL
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def diagnose_incident(
        self, alert_text: str, memories: Optional[List[Dict[str, Any]]] = None, max_retries: int = 2
    ) -> Dict[str, Any]:
        """
        Diagnose an incident using Groq API with retries and fallback model handling.
        Returns a dictionary containing 'diagnosis' (str) and 'suggested_steps' (list of str).
        """
        if not GROQ_API_KEY or GROQ_API_KEY.startswith("your_"):
            logger.info("GROQ_API_KEY not configured or dummy key present. Using fallback response generator.")
            return self._fallback_response(alert_text, memories)

        prompt = self._build_prompt(alert_text, memories)
        models = [PRIMARY_MODEL, FALLBACK_MODEL]

        for model in models:
            for attempt in range(max_retries):
                try:
                    logger.info(f"Calling LLM model '{model}' (Attempt {attempt + 1}/{max_retries})...")
                    response = self.client.chat.completions.create(
                        model=model,
                        messages=[
                            {
                                "role": "system",
                                "content": (
                                    "You are an expert site reliability engineer (SRE) on-call assistant. "
                                    "Analyze the given system alert and optional past incident memories. "
                                    "Provide a JSON response with exactly two fields:\n"
                                    "1. 'diagnosis': A detailed explanation of what is causing the alert.\n"
                                    "2. 'suggested_steps': A list of clear, step-by-step remediation commands/actions.\n"
                                    "Respond ONLY with valid JSON."
                                ),
                            },
                            {"role": "user", "content": prompt},
                        ],
                        response_format={"type": "json_object"},
                        temperature=0.2,
                    )
                    raw_content = response.choices[0].message.content or ""
                    parsed = self._parse_json_response(raw_content)
                    if parsed:
                        return parsed
                except Exception as e:
                    logger.warning(f"LLM call to model '{model}' attempt {attempt + 1} failed: {e}")
                    time.sleep(0.2 * (attempt + 1))

            logger.warning(f"All attempts for primary model '{model}' failed. Trying fallback model if available.")

        # Fallback response if API calls fail or credentials are missing/invalid
        return self._fallback_response(alert_text, memories)

    def _build_prompt(self, alert_text: str, memories: Optional[List[Dict[str, Any]]]) -> str:
        prompt_parts = [f"ALERT TEXT:\n{alert_text}\n"]
        if memories:
            prompt_parts.append("RECALLED PAST INCIDENTS & FEEDBACK MEMORIES:")
            for idx, mem in enumerate(memories, 1):
                prompt_parts.append(f"\n--- Memory #{idx} ---")
                if isinstance(mem, dict):
                    content = mem.get("content") or mem.get("text") or mem.get("fact") or str(mem)
                    context = mem.get("context")
                    prompt_parts.append(f"Content: {content}")
                    if context:
                        prompt_parts.append(f"Context: {context}")
                else:
                    prompt_parts.append(str(mem))
        else:
            prompt_parts.append("NOTE: Hindsight memory is DISABLED for this diagnosis. Diagnose using general knowledge only.")

        prompt_parts.append("\nReturn JSON format:\n{\n  \"diagnosis\": \"...\",\n  \"suggested_steps\": [\"...\"]\n}")
        return "\n".join(prompt_parts)

    def _parse_json_response(self, text: str) -> Optional[Dict[str, Any]]:
        try:
            cleaned = text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

            data = json.loads(cleaned)
            diagnosis = data.get("diagnosis", "")
            suggested_steps = data.get("suggested_steps", [])
            if isinstance(suggested_steps, str):
                suggested_steps = [suggested_steps]
            return {
                "diagnosis": str(diagnosis),
                "suggested_steps": [str(s) for s in suggested_steps],
            }
        except Exception as e:
            logger.error(f"Failed to parse JSON response from LLM: {e}")
            return None

    def _fallback_response(self, alert_text: str, memories: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
        """Provides a heuristic-based response when external LLM service is unavailable."""
        if memories:
            mem_summary = " ".join([str(m.get("content", m)) for m in memories if isinstance(m, dict)])
            if "connection pool" in mem_summary.lower() or "hikari" in mem_summary.lower() or "too many clients" in mem_summary.lower():
                return {
                    "diagnosis": "Based on recalled Hindsight memories, the system is experiencing Database Connection Pool Exhaustion due to leaking connections or unclosed sessions in the auth-service OAuth token generator.",
                    "suggested_steps": [
                        "Inspect active database connections via `SELECT count(*) FROM pg_stat_activity;`",
                        "Verify connection pool configuration max_connections and leak detection settings.",
                        "Restart affected service worker pods to release hung connections.",
                        "Wrap database calls in try-with-resources or proper context managers as applied in INC-1001."
                    ]
                }

        return {
            "diagnosis": f"Incident analysis for alert: '{alert_text[:100]}...'. Potential resource contention or endpoint execution timeout detected.",
            "suggested_steps": [
                "Inspect system CPU, memory, and database metrics.",
                "Review recent service deployments or configuration changes.",
                "Check service error logs for stack traces and exception details."
            ]
        }
