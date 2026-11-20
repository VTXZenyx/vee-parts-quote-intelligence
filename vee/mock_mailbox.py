"""Side-effect-free normalization of *synthetic* Gmail and Graph inbox events.

No network, provider access, database mutation, approval or sending occurs here.
"""
from __future__ import annotations

import heapq
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Mapping, Sequence
from uuid import UUID, uuid5

Provider = Literal["gmail", "graph"]
NAMESPACE = UUID("2b6a41fd-ea24-4761-849c-3c5f20b7ca51")
ADDRESS = re.compile(r"^[^\s<>@]+@[^\s<>@]+\.[^\s<>@]+$")


@dataclass(frozen=True)
class MockMessage:
    provider: Provider
    message_id: str
    thread_id: str
    sender: str
    subject: str
    body: str
    received_at: datetime
    reply_to: str | None

    @property
    def receipt_id(self) -> str:
        return str(uuid5(NAMESPACE, f"{self.provider}:{self.message_id}"))


@dataclass(frozen=True)
class MockThread:
    provider: Provider
    thread_id: str
    messages: tuple[MockMessage, ...]


def _text(value: Any, name: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} requires nonempty text of at most {limit} characters.")
    if any(ord(c) < 32 or ord(c) == 127 for c in value if c not in "\n\t"):
        raise ValueError(f"{name} contains control characters.")
    return value.strip()


def _id(value: Any, name: str) -> str:
    value = _text(value, name, 512)
    if any(c.isspace() for c in value):
        raise ValueError(f"{name} cannot contain whitespace.")
    return value


def _date(value: Any) -> datetime:
    value = _text(value, "timestamp", 64)
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Timestamp must be ISO 8601.") from error
    if date.tzinfo is None or date.utcoffset() is None:
        raise ValueError("Timestamp requires a timezone offset.")
    return date.astimezone(UTC)


def normalise_mock(provider: Provider, payload: Mapping[str, Any]) -> MockMessage:
    """Validate only the documented plain-text mock envelope format."""
    if provider not in ("gmail", "graph") or not isinstance(payload, Mapping):
        raise ValueError("Expected a synthetic Gmail or Graph envelope.")
    message_id = _id(payload.get("id"), "message ID")
    if provider == "gmail":
        thread = _id(payload.get("threadId"), "thread ID")
        sender = _text(payload.get("from"), "sender", 320)
        body = _text(payload.get("textBody"), "plain text", 8000)
        stamp = _date(payload.get("receivedAt"))
        parent = payload.get("inReplyTo")
    else:
        thread = _id(payload.get("conversationId"), "thread ID")
        from_field = payload.get("from")
        if not isinstance(from_field, Mapping) or not isinstance(from_field.get("emailAddress"), Mapping):
            raise ValueError("Graph sender needs emailAddress.address.")
        sender = _text(from_field["emailAddress"].get("address"), "sender", 320)
        value = payload.get("body")
        if not isinstance(value, Mapping) or not isinstance(value.get("contentType"), str) or value["contentType"].casefold() != "text":
            raise ValueError("Graph mock message must contain plain-text content, not HTML.")
        body = _text(value.get("content"), "plain text", 8000)
        stamp = _date(payload.get("receivedDateTime"))
        parent = payload.get("inReplyToId")
    if not ADDRESS.fullmatch(sender):
        raise ValueError("Invalid synthetic sender email address.")
    subject = _text(payload.get("subject"), "subject", 200)
    return MockMessage(provider, message_id, thread, sender, subject, body, stamp,
                       _id(parent, "reply parent ID") if parent is not None else None)


def plan_mock_import(events: Sequence[tuple[Provider, Mapping[str, Any]]]) -> tuple[MockThread, ...]:
    """Preview idempotent threads from mock delivery batches, without writing data.

    A thread needs exactly one root, and every reply must have an in-batch parent.
    A future incremental importer will need persisted provider message IDs and an
    explicitly reviewed decision for how to handle incomplete conversations.
    """
    unique: dict[tuple[Provider, str], MockMessage] = {}
    for provider, payload in events:
        message = normalise_mock(provider, payload)
        key = provider, message.message_id
        if key in unique and unique[key] != message:
            raise ValueError(f"Conflicting deliveries for {provider} message {message.message_id}.")
        unique[key] = message
    grouped: dict[tuple[Provider, str], dict[str, MockMessage]] = {}
    for message in unique.values():
        grouped.setdefault((message.provider, message.thread_id), {})[message.message_id] = message

    result = []
    for (provider, thread_id), messages in sorted(grouped.items()):
        roots = [msg for msg in messages.values() if msg.reply_to is None]
        if len(roots) != 1:
            raise ValueError(f"Thread {provider}/{thread_id} requires exactly one root.")
        children: dict[str, list[str]] = {key: [] for key in messages}
        for message in messages.values():
            if message.reply_to is not None:
                if message.reply_to not in messages:
                    raise ValueError(f"Reply {message.message_id} has no parent in its own thread.")
                children[message.reply_to].append(message.message_id)
        root = roots[0]
        queue = [(root.received_at, root.message_id)]
        ordered = []
        while queue:
            _, mid = heapq.heappop(queue)
            ordered.append(messages[mid])
            for child_id in children[mid]:
                child = messages[child_id]
                heapq.heappush(queue, (child.received_at, child_id))
        if len(ordered) != len(messages):
            raise ValueError(f"Thread {provider}/{thread_id} has cyclic or disconnected replies.")
        result.append(MockThread(provider, thread_id, tuple(ordered)))
    return tuple(result)
