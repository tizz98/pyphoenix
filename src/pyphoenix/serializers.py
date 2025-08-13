"""Message serialization and deserialization for PyPhoenix."""

import json
import pickle
from abc import ABC, abstractmethod
from typing import Any

try:
    import msgpack

    MSGPACK_AVAILABLE = True
except ImportError:
    MSGPACK_AVAILABLE = False

import structlog

from .exceptions import SerializationError

logger = structlog.get_logger(__name__)


class Serializer(ABC):
    """Base class for message serializers."""

    @abstractmethod
    def serialize(self, data: Any) -> bytes:
        """Serialize data to bytes."""
        pass

    @abstractmethod
    def deserialize(self, data: bytes) -> Any:
        """Deserialize bytes to data."""
        pass

    @property
    @abstractmethod
    def content_type(self) -> str:
        """Get the content type for this serializer."""
        pass


class JSONSerializer(Serializer):
    """JSON-based message serializer."""

    def serialize(self, data: Any) -> bytes:
        """Serialize data to JSON bytes."""
        try:
            return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError) as e:
            raise SerializationError(f"Failed to serialize to JSON: {e}") from e

    def deserialize(self, data: bytes) -> Any:
        """Deserialize JSON bytes to data."""
        try:
            return json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise SerializationError(f"Failed to deserialize JSON: {e}") from e

    @property
    def content_type(self) -> str:
        return "application/json"


class PickleSerializer(Serializer):
    """Pickle-based message serializer (not recommended for network use)."""

    def serialize(self, data: Any) -> bytes:
        """Serialize data to pickle bytes."""
        try:
            return pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL)
        except (pickle.PicklingError, TypeError) as e:
            raise SerializationError(f"Failed to serialize with pickle: {e}") from e

    def deserialize(self, data: bytes) -> Any:
        """Deserialize pickle bytes to data."""
        try:
            return pickle.loads(data)
        except (pickle.UnpicklingError, TypeError) as e:
            raise SerializationError(f"Failed to deserialize pickle: {e}") from e

    @property
    def content_type(self) -> str:
        return "application/x-pickle"


class MessagePackSerializer(Serializer):
    """MessagePack-based message serializer."""

    def __init__(self):
        if not MSGPACK_AVAILABLE:
            raise ImportError("msgpack is required for MessagePackSerializer")

    def serialize(self, data: Any) -> bytes:
        """Serialize data to MessagePack bytes."""
        try:
            return msgpack.packb(data, use_bin_type=True)
        except (msgpack.exceptions.PackException, TypeError) as e:
            raise SerializationError(f"Failed to serialize with MessagePack: {e}") from e

    def deserialize(self, data: bytes) -> Any:
        """Deserialize MessagePack bytes to data."""
        try:
            return msgpack.unpackb(data, raw=False, strict_map_key=False)
        except (
            msgpack.exceptions.UnpackException,
            msgpack.exceptions.ExtraData,
            ValueError,
        ) as e:
            raise SerializationError(f"Failed to deserialize MessagePack: {e}") from e

    @property
    def content_type(self) -> str:
        return "application/msgpack"


class SerializerRegistry:
    """Registry for managing message serializers."""

    def __init__(self):
        self._serializers: dict[str, Serializer] = {}
        self._default_serializer: str = "json"

        # Register built-in serializers
        self.register("json", JSONSerializer())
        self.register("pickle", PickleSerializer())

        if MSGPACK_AVAILABLE:
            self.register("msgpack", MessagePackSerializer())

    def register(self, name: str, serializer: Serializer) -> None:
        """Register a serializer."""
        self._serializers[name] = serializer
        logger.debug("serializer.registered", name=name, content_type=serializer.content_type)

    def unregister(self, name: str) -> None:
        """Unregister a serializer."""
        if name in self._serializers:
            del self._serializers[name]
            logger.debug("serializer.unregistered", name=name)

    def get(self, name: str) -> Serializer:
        """Get a serializer by name."""
        if name not in self._serializers:
            raise ValueError(f"Unknown serializer: {name}")
        return self._serializers[name]

    def set_default(self, name: str) -> None:
        """Set the default serializer."""
        if name not in self._serializers:
            raise ValueError(f"Unknown serializer: {name}")
        self._default_serializer = name
        logger.info("serializer.default_changed", name=name)

    def get_default(self) -> Serializer:
        """Get the default serializer."""
        return self.get(self._default_serializer)

    def list_serializers(self) -> list[str]:
        """List all registered serializers."""
        return list(self._serializers.keys())


# Global serializer registry
_serializer_registry: SerializerRegistry | None = None


def get_serializer_registry() -> SerializerRegistry:
    """Get the global serializer registry."""
    global _serializer_registry
    if _serializer_registry is None:
        _serializer_registry = SerializerRegistry()
    return _serializer_registry
