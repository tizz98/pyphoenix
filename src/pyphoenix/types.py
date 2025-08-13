"""Core types and data structures for PyPhoenix."""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal


class ChannelState(Enum):
    """Channel connection states."""

    CLOSED = "closed"
    ERRORED = "errored"
    JOINED = "joined"
    JOINING = "joining"
    LEAVING = "leaving"


@dataclass
class JoinResponse:
    """Response from joining a channel."""

    status: Literal["ok", "error"]
    response: dict[str, Any]

    @property
    def is_ok(self) -> bool:
        return self.status == "ok"

    @property
    def is_error(self) -> bool:
        return self.status == "error"


@dataclass
class PushResponse:
    """Response from pushing a message to a channel."""

    status: Literal["ok", "error", "timeout"]
    response: dict[str, Any]
    ref: str | None = None

    @property
    def is_ok(self) -> bool:
        return self.status == "ok"

    @property
    def is_error(self) -> bool:
        return self.status == "error"

    @property
    def is_timeout(self) -> bool:
        return self.status == "timeout"


@dataclass
class Message:
    """Phoenix message structure."""

    topic: str
    event: str
    payload: dict[str, Any]
    ref: str | None = None
    join_ref: str | None = None

    def to_list(self) -> list:
        """Convert to Phoenix wire format [join_ref, ref, topic, event, payload]."""
        return [self.join_ref, self.ref, self.topic, self.event, self.payload]

    @classmethod
    def from_list(cls, data: list) -> "Message":
        """Create message from Phoenix wire format."""
        join_ref, ref, topic, event, payload = data
        return cls(topic=topic, event=event, payload=payload, ref=ref, join_ref=join_ref)


@dataclass
class PresenceMeta:
    """Metadata for presence tracking."""

    online_at: float
    user_id: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class PresenceState:
    """State of a presence entry."""

    metas: list[PresenceMeta]

    @property
    def first_meta(self) -> PresenceMeta | None:
        """Get the first (oldest) meta entry."""
        return self.metas[0] if self.metas else None
