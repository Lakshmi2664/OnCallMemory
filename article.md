# I ran Hindsight calls in their own event loops to avoid reusing aiohttp sessions

The first memory bug I cared about was not whether an incident could be recalled. It was whether the client doing the recall could safely make the next network request. Hindsight’s Python client sits at an awkward boundary in a synchronous FastAPI application: the API handlers are ordinary functions, while the underlying HTTP stack can carry event-loop-bound state. I chose to give each Hindsight operation a worker thread, a fresh event loop, and a fresh client instance.

That decision shaped the rest of OnCallMemory. The service keeps incident memory outside the request process, asks Hindsight for relevant prior incidents when an alert arrives, and passes those records to an LLM alongside the live alert. Resolutions can be recorded as feedback for later retrieval. The interesting engineering question was not how to add “memory” to a prompt. It was how to put a stateful memory client behind a straightforward request-response API without letting its async plumbing leak through every layer.

## The request path

OnCallMemory is an incident-response service built around a small set of operations. `/seed` retains incident post-mortems, `/incident` optionally recalls relevant memories and returns a diagnosis, `/feedback` retains whether a proposed fix worked, and `/patterns` asks Hindsight to reflect across the bank. A single configured bank identifies the team’s memory space.

The incident handler makes the memory decision explicit. With memory enabled, it calls `recall_memories()` using the alert text. It formats returned records into the LLM request, including content and relevance score. With memory disabled, it skips recall and tells the model that persistent memory is off. Either way, the response includes a `recalled_memories` field, so the caller can see what historical context informed the answer.

This is useful operationally. A database connection pool alert can be interpreted in light of an earlier pool exhaustion and its verified fix, while a memory-off request gives a clean path that does not query Hindsight. The system does not assume every alert has a matching precedent, either: an empty recall is represented explicitly and the diagnosis still proceeds.

The memory service has three jobs. It converts structured incident reports into readable retained content, normalizes recall responses into a stable shape for the API, and turns reflection responses into text. The LLM adapter separately owns retries and model fallback. That division keeps Hindsight-specific concerns out of the prompt orchestration and keeps provider retries out of the memory wrapper.

## The boundary that mattered: one event loop per call

The central implementation choice is in `hindsight_services.py`. Rather than share one client across FastAPI requests, the wrapper submits each operation to a small thread pool. The worker constructs the client and event loop together, invokes a single method, then closes the loop.

```python
def _run_in_new_loop(method_name, base_url, api_key, bank_id, *args, **kwargs):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        client = Hindsight(base_url=base_url, api_key=api_key, timeout=60.0)
        method = getattr(client, method_name)
        return method(bank_id, *args, **kwargs)
    finally:
        loop.close()
```

The comment in the code names the motivating risk: aiohttp session reuse across event loops. The important constraint is ownership. A client and any loop-bound resources it creates are made and used within the worker’s loop instead of being carried between unrelated request contexts. Creating the client inside the worker also avoids constructing it on the FastAPI thread and then handing it to another loop.

The synchronous boundary is equally deliberate:

```python
def _safe_run(self, method_name, *args, **kwargs):
    future = executor.submit(
        _run_in_new_loop, method_name, self.base_url, self.api_key,
        self.bank_id, *args, **kwargs
    )
    return future.result(timeout=90)
```

The rest of the service can call `_safe_run()` like an ordinary blocking dependency. FastAPI handlers can stay synchronous; `recall_memories()` can return a list rather than an awaitable; and the endpoint code does not need to know how the HTTP client manages its async internals.

This is a containment strategy, not a claim that threads make async code simpler in every application. The API call blocks while waiting for the worker result. The executor has five workers, so there is a defined bound on concurrent Hindsight operations, but enough slow operations can occupy all of them. The 90-second wait is also a timeout for the caller; it should not be mistaken for proof that the underlying work was cancelled. Those are production concerns to measure and handle with request-level limits, observability, and explicit cancellation semantics.

I prefer this seam to spreading event-loop management through the endpoint layer. The tradeoff is visible in one wrapper, and the rest of the application speaks in terms of retain, recall, and reflect. If the application later becomes fully asynchronous, this boundary is the obvious place to revisit: either use a supported async client interface end to end or keep this isolated adapter and account for its blocking behavior.

## Memory needs outcomes, not just history

A post-mortem is valuable context, but it does not say whether a particular suggested action actually worked when tried again. The feedback endpoint therefore records both the proposed fix and its outcome. The wrapper writes a plain-language record into the same Hindsight bank:

```python
status = "SUCCESSFUL / WORKED" if worked else "FAILED / DID NOT WORK"
content = (
    f"Feedback for Incident: {incident_id}\n"
    f"Suggested Fix: {suggestion}\n"
    f"Outcome: {status}\n"
    f"Notes: {notes or 'None'}"
)
```

The phrasing is intentionally direct. A future recall should have the suggestion and the result together, not merely a note that someone investigated an incident. Successful feedback can support a future recommendation; failed feedback can warn against repeating an attempted step. It does not guarantee that retrieval will find the feedback or that the LLM will weigh it correctly. It does make the outcome available as memory rather than leaving it trapped in a ticket comment or a person’s recollection.

Historical incidents are retained with service, symptoms, error log, metrics, root cause, fix, and time to resolve. This gives recall more than a short incident title to match against. The configured bank scopes those records to the team. Hindsight provides the retain, recall, and reflect primitives; the project’s wrapper defines what operational facts are stored and how they enter diagnosis. Engineers can explore the [Hindsight GitHub repository](https://github.com/vectorize-io/hindsight), its [Hindsight memory documentation](https://hindsight.vectorize.io/), and Vectorize’s overview of [agent memory and persistent context](https://vectorize.io/what-is-agent-memory) for the underlying concepts.

## What an interaction looks like

Imagine an alert containing a SQLAlchemy `QueuePool` timeout and a high database connection count. The handler submits the alert text as the recall query. Hindsight may return a prior checkout incident that also involved connection exhaustion, with its root cause and fix retained in the content. The service reshapes each result to `content`, `score`, and `context`, regardless of whether the client returned dictionaries or objects.

The handler then places those memories beside the incoming alert in the LLM context. The model is asked for JSON containing a diagnosis and remediation steps. The API returns that diagnosis, those steps, and the memories used. If the operator applies a step, the client can post its outcome to `/feedback`; that outcome becomes another retained memory. Later, `/patterns` can request a reflection such as recurring incident causes across the bank.

The crucial property is traceability of context. The caller can inspect which memories were recalled, and can disable memory for a request. That is better than silently blending retrieved material into a diagnosis with no way to see where it came from. It also gives us a practical comparison mechanism: run otherwise similar requests with memory enabled and disabled, then inspect both the answer and the recalled records. The code enables that comparison; it does not establish that memory improves accuracy in every case.

## Lessons I would carry into another service

1. **Make async ownership local.** If a library holds event-loop-bound resources, construct and use them under the same loop. A small adapter is easier to audit than implicit cross-loop reuse.
2. **Keep the boundary honest.** A thread pool makes an async dependency callable from synchronous code; it does not make the call non-blocking from the request’s perspective. Capacity, deadlines, cancellation, and queueing still need operational attention.
3. **Store outcomes with recommendations.** For incident response, “we tried this” is weaker than “we tried this and it failed.” Retaining both makes later recall more useful and less one-sided.
4. **Return the evidence used.** Including recalled memories in the response gives operators a way to inspect the historical context behind a diagnosis.
5. **Treat memory as an input that can be absent.** No recall, an unavailable memory service, and memory intentionally disabled are distinct conditions. The diagnosis path should remain understandable in each case.

The larger design lesson is that persistent memory is not just a retrieval call bolted onto a prompt. It becomes part of the service’s reliability surface: it has client lifecycle, capacity, failure behavior, data shape, and operator visibility. Isolating Hindsight behind a narrow service wrapper let me make those choices explicit. That is the piece I would preserve as the system grows, even if the surrounding API and deployment architecture change.
