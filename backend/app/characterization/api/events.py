"""Server-Sent Events (SSE) generator for live characterization progress."""

import json
from typing import Any, AsyncGenerator, Dict


async def sse_event_stream(
    event_generator: AsyncGenerator[Dict[str, Any], None]
) -> AsyncGenerator[str, None]:
    """Format dictionary event payloads into text/event-stream chunks."""
    async for event in event_generator:
        event_name = event.get("event_type", "message")
        data_str = json.dumps(event, default=str)
        yield f"event: {event_name}\ndata: {data_str}\n\n"

