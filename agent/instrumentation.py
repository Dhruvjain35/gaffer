"""Phoenix tracing via OpenInference auto-instrumentation of ADK.

Pattern from Arize's official hackathon starter (Arize-ai/gemini-hackathon):
``register(..., auto_instrument=True)`` hooks every ADK LLM call and tool call.

Env: PHOENIX_API_KEY, PHOENIX_COLLECTOR_ENDPOINT (incl. /s/<space>), PHOENIX_PROJECT_NAME.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from phoenix.otel import register

_provider: Optional[Any] = None


def setup_tracing() -> Optional[Any]:
    """Idempotent. Returns the tracer provider, or None when Phoenix isn't configured."""
    global _provider
    if _provider is not None:
        return _provider
    if not (os.environ.get("PHOENIX_API_KEY") or "").strip():
        return None
    _provider = register(
        project_name=os.environ.get("PHOENIX_PROJECT_NAME", "gaffer"),
        batch=False,  # immediate export: the Gaffer reviews tape seconds after a turn
        auto_instrument=True,
        verbose=False,
    )
    # replace_default_processor=False: keep Phoenix's OTLP exporter alongside our recorder
    _provider.add_span_processor(_RootSpanRecorder(), replace_default_processor=False)
    return _provider


from opentelemetry.sdk.trace import SpanProcessor


class _RootSpanRecorder(SpanProcessor):
    """Span processor that remembers recent root (parentless) spans so the
    server can annotate the exact span a judge verdict belongs to and deep-link
    each answer to its Phoenix trace."""

    def on_start(self, span, parent_context=None):  # noqa: D102
        pass

    def on_end(self, span) -> None:  # noqa: D102
        try:
            if span.parent is None:
                ROOT_SPANS.append(
                    {
                        "span_id": format(span.context.span_id, "016x"),
                        "trace_id": format(span.context.trace_id, "032x"),
                        "name": span.name,
                        "end_time": span.end_time,
                    }
                )
                del ROOT_SPANS[:-50]
        except Exception:  # noqa: BLE001 — observability must never crash the app
            pass

    def shutdown(self) -> None:  # noqa: D102
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:  # noqa: D102
        return True


ROOT_SPANS: list[dict] = []


def latest_root_span() -> dict | None:
    return ROOT_SPANS[-1] if ROOT_SPANS else None
