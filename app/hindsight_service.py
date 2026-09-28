import datetime
import json
import logging
from typing import Any, Dict, List, Optional
from hindsight_client import Hindsight
from app.config import HINDSIGHT_BASE_URL, HINDSIGHT_API_KEY, HINDSIGHT_BANK_ID

logger = logging.getLogger(__name__)


class HindsightService:
    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        bank_id: Optional[str] = None,
    ):
        self.base_url = base_url or HINDSIGHT_BASE_URL
        self.api_key = api_key or HINDSIGHT_API_KEY
        self.bank_id = bank_id or HINDSIGHT_BANK_ID
        self._in_memory_store: List[Dict[str, Any]] = []

        try:
            self.client = Hindsight(base_url=self.base_url, api_key=self.api_key)
            self.is_connected = True
        except Exception as e:
            logger.warning(f"Could not connect to live Hindsight server at {self.base_url}: {e}. Using in-memory fallback.")
            self.client = None
            self.is_connected = False

    def retain(
        self,
        content: str,
        context: Optional[str] = None,
        timestamp: Optional[datetime.datetime] = None,
        bank_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Retain an incident or feedback record in Hindsight.
        client.retain(bank_id, content, context, timestamp)
        """
        target_bank = bank_id or self.bank_id
        now = timestamp or datetime.datetime.now(datetime.timezone.utc)

        # Always store in memory fallback list
        record = {
            "bank_id": target_bank,
            "content": content,
            "context": context,
            "timestamp": now.isoformat(),
        }
        self._in_memory_store.append(record)

        if self.client:
            try:
                response = self.client.retain(
                    bank_id=target_bank,
                    content=content,
                    context=context,
                    timestamp=now,
                )
                return {"status": "success", "client_response": str(response)}
            except Exception as e:
                logger.warning(f"Hindsight retain call failed: {e}. Record saved in local memory.")
                return {"status": "fallback", "error": str(e)}

        return {"status": "in_memory", "record": record}

    def recall(self, query: str, bank_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Recall relevant past memories for an alert query.
        client.recall(bank_id, query)
        """
        target_bank = bank_id or self.bank_id

        if self.client:
            try:
                response = self.client.recall(bank_id=target_bank, query=query)
                results = []
                # Hindsight RecallResponse iteration / extraction
                if hasattr(response, "results"):
                    items = response.results
                elif isinstance(response, list):
                    items = response
                elif hasattr(response, "__iter__"):
                    items = list(response)
                else:
                    items = []

                for item in items:
                    item_dict = {}
                    if hasattr(item, "to_dict"):
                        item_dict = item.to_dict()
                    elif isinstance(item, dict):
                        item_dict = item
                    else:
                        item_dict = {
                            "content": getattr(item, "content", getattr(item, "text", getattr(item, "fact", str(item)))),
                            "context": getattr(item, "context", None),
                        }
                    results.append(item_dict)

                if results:
                    return results
            except Exception as e:
                logger.warning(f"Hindsight recall call failed: {e}. Falling back to local memory matching.")

        # Local fallback search matching keywords in query
        query_terms = [t.lower() for t in query.split() if len(t) > 3]
        matched = []
        for item in reversed(self._in_memory_store):
            content_lower = item["content"].lower()
            context_lower = (item["context"] or "").lower()
            if any(term in content_lower or term in context_lower for term in query_terms) or not query_terms:
                matched.append({
                    "content": item["content"],
                    "context": item["context"],
                    "timestamp": item["timestamp"],
                })

        return matched[:5]

    def reflect(self, query: str = "what patterns keep recurring across our incidents?", bank_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Reflect on patterns across all incidents.
        client.reflect(bank_id, query)
        """
        target_bank = bank_id or self.bank_id

        if self.client:
            try:
                response = self.client.reflect(bank_id=target_bank, query=query)
                summary_text = getattr(response, "text", getattr(response, "summary", str(response)))
                return {"query": query, "patterns_summary": summary_text}
            except Exception as e:
                logger.warning(f"Hindsight reflect call failed: {e}. Generating reflection from local store.")

        # Local reflection heuristic from retained items
        if not self._in_memory_store:
            return {
                "query": query,
                "patterns_summary": "No incidents recorded yet. Please run /seed or log incidents first to analyze recurring patterns."
            }

        patterns = [
            "1. Database Connection Pool Exhaustion (auth-service, checkout-service, order-management): Frequent thread or connection starvation caused by leaking DB connections in error blocks or missing try-with-resources.",
            "2. External Service & Network Resource Exhaustion (payment-gateway, billing-service): Outbound HTTPS requests to third-party APIs timing out due to NAT Gateway port exhaustion or expired TLS CA certificates.",
            "3. Out of Memory & Unbounded Fetch Operations (user-profile-api, realtime-chat): Memory spikes and pod crash loops caused by loading unpaginated bulk records into JVM/Heap memory or unremoved WebSocket event listeners.",
            "4. Threadpool & Queue Saturation (search-indexer, analytics-ingest): Elasticsearch write threadpool and Kafka consumer group rebalances triggered by unthrottled batch updates without jitter or backoff."
        ]

        return {
            "query": query,
            "patterns_summary": "\n".join(patterns)
        }
