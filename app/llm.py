import json
import logging
import time
from typing import List, Dict, Any, Optional
from openai import OpenAI, OpenAIError
from app.config import GROQ_BASE_URL, GROQ_API_KEY, PRIMARY_MODEL, FALLBACK_MODEL

logger = logging.getLogger("oncall_memory.llm")

def get_openai_client() -> OpenAI:
    api_key = GROQ_API_KEY or "dummy-key"
    return OpenAI(
        base_url=GROQ_BASE_URL,
        api_key=api_key,
    )

def call_llm_with_retry(
    messages: List[Dict[str, str]],
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Optional[Any] = None,
    response_format: Optional[Dict[str, Any]] = None,
    max_retries: int = 3,
) -> str:
    """
    Calls Groq LLM using OpenAI-compatible client.
    Wraps all calls with retry logic, exponential backoff, and fallback model handling.
    Gracefully handles function-calling or response parsing errors.
    """
    client = get_openai_client()
    models_to_try = [PRIMARY_MODEL, FALLBACK_MODEL]

    for model in models_to_try:
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"Attempting LLM call with model {model} (Attempt {attempt}/{max_retries})")

                kwargs: Dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "temperature": 0.2,
                }
                if tools:
                    kwargs["tools"] = tools
                if tool_choice:
                    kwargs["tool_choice"] = tool_choice
                if response_format:
                    kwargs["response_format"] = response_format

                response = client.chat.completions.create(**kwargs)
                choice = response.choices[0]
                message = choice.message

                # Handle tool calls if present
                if hasattr(message, "tool_calls") and message.tool_calls:
                    tool_call = message.tool_calls[0]
                    return tool_call.function.arguments

                content = message.content or ""
                if content:
                    return content.strip()

            except Exception as e:
                logger.warning(f"LLM call failed for model {model} on attempt {attempt}: {str(e)}")
                if attempt < max_retries:
                    time.sleep(2 ** (attempt - 1))  # Exponential backoff: 1s, 2s, 4s
                else:
                    logger.error(f"Exhausted retries for model {model}. Falling back to next model if available.")

    # Graceful fallback response if all LLM API attempts fail (e.g. invalid API key or offline network)
    logger.error("All LLM models and retries failed. Returning fallback structured error response.")
    return json.dumps({
        "diagnosis": "Unable to perform automated diagnosis due to upstream LLM service unavailability. Please check Groq API configuration and network connectivity.",
        "suggested_steps": [
            "Check Groq API key and rate limits",
            "Review error logs directly in logging dashboard",
            "Verify network reachability to model endpoint"
        ]
    })
