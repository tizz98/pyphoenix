"""PyPhoenix: Real-time Communication Library for Python."""

# Core components
from .channel import Channel

# Client components
from .client import ClientChannel, ClientSocket

# Configuration and middleware
from .config import PhoenixConfig, get_config, set_config

# Types and exceptions
from .exceptions import (
    AuthenticationError,
    AuthorizationError,
    ChannelError,
    ConnectionError,
    JoinError,
    PresenceError,
    PubSubError,
    PushError,
    PyPhoenixError,
    SerializationError,
    TimeoutError,
)

# Metrics and monitoring
from .metrics import (
    MetricsRegistry,
    PhoenixMetrics,
    get_metrics_registry,
    get_phoenix_metrics,
)
from .middleware import (
    AuthMiddleware,
    LoggingMiddleware,
    Middleware,
    MiddlewareStack,
    RateLimitMiddleware,
)
from .phoenix import Phoenix, create_app
from .presence import Presence, get_presence
from .pubsub import PubSub, get_pubsub

# Serialization
from .serializers import (
    JSONSerializer,
    MessagePackSerializer,
    Serializer,
    SerializerRegistry,
    get_serializer_registry,
)
from .socket import Socket, WebSocketTransport
from .types import (
    ChannelState,
    JoinResponse,
    Message,
    PresenceMeta,
    PresenceState,
    PushResponse,
)

__version__ = "0.1.0"

__all__ = [
    # Core API
    "Phoenix",
    "create_app",
    "Channel",
    "Socket",
    "WebSocketTransport",
    "PubSub",
    "get_pubsub",
    "Presence",
    "get_presence",
    # Client API
    "ClientSocket",
    "ClientChannel",
    # Configuration
    "PhoenixConfig",
    "get_config",
    "set_config",
    # Middleware
    "Middleware",
    "LoggingMiddleware",
    "AuthMiddleware",
    "RateLimitMiddleware",
    "MiddlewareStack",
    # Metrics
    "MetricsRegistry",
    "PhoenixMetrics",
    "get_metrics_registry",
    "get_phoenix_metrics",
    # Serialization
    "Serializer",
    "JSONSerializer",
    "MessagePackSerializer",
    "SerializerRegistry",
    "get_serializer_registry",
    # Types
    "ChannelState",
    "JoinResponse",
    "PushResponse",
    "Message",
    "PresenceMeta",
    "PresenceState",
    # Exceptions
    "PyPhoenixError",
    "ChannelError",
    "JoinError",
    "PushError",
    "ConnectionError",
    "AuthenticationError",
    "AuthorizationError",
    "PresenceError",
    "PubSubError",
    "SerializationError",
    "TimeoutError",
]
