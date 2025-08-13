"""Configuration system for PyPhoenix."""

import os
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ChannelConfig:
    """Configuration for channel behavior."""

    default_timeout: float = 10.0
    max_join_timeout: float = 30.0
    rejoin_delay: float = 5.0
    max_push_buffer_size: int = 100
    enable_middleware: bool = True


@dataclass
class PubSubConfig:
    """Configuration for PubSub system."""

    message_ttl: float = 300.0  # 5 minutes
    max_topic_length: int = 255
    max_subscribers_per_topic: int = 1000
    enable_pattern_matching: bool = True
    delivery_guarantee: str = "at_least_once"  # "at_most_once", "at_least_once", "exactly_once"


@dataclass
class PresenceConfig:
    """Configuration for presence tracking."""

    heartbeat_interval: float = 30.0
    presence_timeout: float = 120.0
    cleanup_interval: float = 300.0  # 5 minutes
    max_presences_per_topic: int = 10000


@dataclass
class TransportConfig:
    """Configuration for transport layer."""

    websocket_ping_interval: float = 20.0
    websocket_ping_timeout: float = 60.0
    max_connections: int = 10000
    max_message_size: int = 64 * 1024  # 64KB
    compression_enabled: bool = True


@dataclass
class SecurityConfig:
    """Configuration for security features."""

    require_authentication: bool = False
    token_expiry: float = 3600.0  # 1 hour
    max_auth_attempts: int = 3
    rate_limit_enabled: bool = True
    max_messages_per_second: int = 10


@dataclass
class LoggingConfig:
    """Configuration for logging."""

    level: str = "INFO"
    structured: bool = True
    include_request_id: bool = True
    log_channel_events: bool = True
    log_presence_events: bool = False


@dataclass
class PhoenixConfig:
    """Main configuration class for PyPhoenix."""

    # Core settings
    host: str = "localhost"
    port: int = 4000
    workers: int = 1
    debug: bool = False

    # Component configurations
    channel: ChannelConfig = field(default_factory=ChannelConfig)
    pubsub: PubSubConfig = field(default_factory=PubSubConfig)
    presence: PresenceConfig = field(default_factory=PresenceConfig)
    transport: TransportConfig = field(default_factory=TransportConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    # Custom settings
    custom: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "PhoenixConfig":
        """Create configuration from environment variables."""
        config = cls()

        # Core settings
        config.host = os.getenv("PYPHOENIX_HOST", config.host)
        config.port = int(os.getenv("PYPHOENIX_PORT", str(config.port)))
        config.workers = int(os.getenv("PYPHOENIX_WORKERS", str(config.workers)))
        config.debug = os.getenv("PYPHOENIX_DEBUG", "").lower() in ("true", "1", "yes")

        # Channel settings
        config.channel.default_timeout = float(
            os.getenv("PYPHOENIX_CHANNEL_TIMEOUT", str(config.channel.default_timeout))
        )
        config.channel.max_join_timeout = float(
            os.getenv("PYPHOENIX_CHANNEL_MAX_JOIN_TIMEOUT", str(config.channel.max_join_timeout))
        )

        # PubSub settings
        config.pubsub.message_ttl = float(
            os.getenv("PYPHOENIX_PUBSUB_MESSAGE_TTL", str(config.pubsub.message_ttl))
        )
        config.pubsub.max_subscribers_per_topic = int(
            os.getenv(
                "PYPHOENIX_PUBSUB_MAX_SUBSCRIBERS",
                str(config.pubsub.max_subscribers_per_topic),
            )
        )

        # Security settings
        config.security.require_authentication = os.getenv(
            "PYPHOENIX_REQUIRE_AUTH", ""
        ).lower() in ("true", "1", "yes")
        config.security.rate_limit_enabled = os.getenv("PYPHOENIX_RATE_LIMIT", "true").lower() in (
            "true",
            "1",
            "yes",
        )
        config.security.max_messages_per_second = int(
            os.getenv(
                "PYPHOENIX_RATE_LIMIT_MPS",
                str(config.security.max_messages_per_second),
            )
        )

        # Logging settings
        config.logging.level = os.getenv("PYPHOENIX_LOG_LEVEL", config.logging.level).upper()
        config.logging.structured = os.getenv("PYPHOENIX_LOG_STRUCTURED", "true").lower() in (
            "true",
            "1",
            "yes",
        )

        logger.info("config.loaded_from_env", config=config)
        return config

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PhoenixConfig":
        """Create configuration from a dictionary."""
        config = cls()

        # Core settings
        config.host = data.get("host", config.host)
        config.port = data.get("port", config.port)
        config.workers = data.get("workers", config.workers)
        config.debug = data.get("debug", config.debug)

        # Channel settings
        if "channel" in data:
            channel_data = data["channel"]
            config.channel.default_timeout = channel_data.get(
                "default_timeout", config.channel.default_timeout
            )
            config.channel.max_join_timeout = channel_data.get(
                "max_join_timeout", config.channel.max_join_timeout
            )
            config.channel.rejoin_delay = channel_data.get(
                "rejoin_delay", config.channel.rejoin_delay
            )

        # PubSub settings
        if "pubsub" in data:
            pubsub_data = data["pubsub"]
            config.pubsub.message_ttl = pubsub_data.get("message_ttl", config.pubsub.message_ttl)
            config.pubsub.max_subscribers_per_topic = pubsub_data.get(
                "max_subscribers_per_topic", config.pubsub.max_subscribers_per_topic
            )
            config.pubsub.delivery_guarantee = pubsub_data.get(
                "delivery_guarantee", config.pubsub.delivery_guarantee
            )

        # Security settings
        if "security" in data:
            security_data = data["security"]
            config.security.require_authentication = security_data.get(
                "require_authentication", config.security.require_authentication
            )
            config.security.rate_limit_enabled = security_data.get(
                "rate_limit_enabled", config.security.rate_limit_enabled
            )
            config.security.max_messages_per_second = security_data.get(
                "max_messages_per_second", config.security.max_messages_per_second
            )

        # Custom settings
        config.custom = data.get("custom", {})

        logger.info("config.loaded_from_dict", config=config)
        return config

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to a dictionary."""
        return {
            "host": self.host,
            "port": self.port,
            "workers": self.workers,
            "debug": self.debug,
            "channel": {
                "default_timeout": self.channel.default_timeout,
                "max_join_timeout": self.channel.max_join_timeout,
                "rejoin_delay": self.channel.rejoin_delay,
                "max_push_buffer_size": self.channel.max_push_buffer_size,
                "enable_middleware": self.channel.enable_middleware,
            },
            "pubsub": {
                "message_ttl": self.pubsub.message_ttl,
                "max_topic_length": self.pubsub.max_topic_length,
                "max_subscribers_per_topic": self.pubsub.max_subscribers_per_topic,
                "enable_pattern_matching": self.pubsub.enable_pattern_matching,
                "delivery_guarantee": self.pubsub.delivery_guarantee,
            },
            "presence": {
                "heartbeat_interval": self.presence.heartbeat_interval,
                "presence_timeout": self.presence.presence_timeout,
                "cleanup_interval": self.presence.cleanup_interval,
                "max_presences_per_topic": self.presence.max_presences_per_topic,
            },
            "transport": {
                "websocket_ping_interval": self.transport.websocket_ping_interval,
                "websocket_ping_timeout": self.transport.websocket_ping_timeout,
                "max_connections": self.transport.max_connections,
                "max_message_size": self.transport.max_message_size,
                "compression_enabled": self.transport.compression_enabled,
            },
            "security": {
                "require_authentication": self.security.require_authentication,
                "token_expiry": self.security.token_expiry,
                "max_auth_attempts": self.security.max_auth_attempts,
                "rate_limit_enabled": self.security.rate_limit_enabled,
                "max_messages_per_second": self.security.max_messages_per_second,
            },
            "logging": {
                "level": self.logging.level,
                "structured": self.logging.structured,
                "include_request_id": self.logging.include_request_id,
                "log_channel_events": self.logging.log_channel_events,
                "log_presence_events": self.logging.log_presence_events,
            },
            "custom": self.custom,
        }

    def validate(self) -> list[str]:
        """Validate configuration and return list of errors."""
        errors = []

        # Validate core settings
        if not isinstance(self.host, str) or not self.host:
            errors.append("host must be a non-empty string")

        if not isinstance(self.port, int) or not (1 <= self.port <= 65535):
            errors.append("port must be an integer between 1 and 65535")

        if not isinstance(self.workers, int) or self.workers < 1:
            errors.append("workers must be a positive integer")

        # Validate channel settings
        if self.channel.default_timeout <= 0:
            errors.append("channel.default_timeout must be positive")

        if self.channel.max_join_timeout <= 0:
            errors.append("channel.max_join_timeout must be positive")

        if self.channel.max_push_buffer_size < 1:
            errors.append("channel.max_push_buffer_size must be at least 1")

        # Validate PubSub settings
        if self.pubsub.message_ttl <= 0:
            errors.append("pubsub.message_ttl must be positive")

        if self.pubsub.max_subscribers_per_topic < 1:
            errors.append("pubsub.max_subscribers_per_topic must be at least 1")

        if self.pubsub.delivery_guarantee not in [
            "at_most_once",
            "at_least_once",
            "exactly_once",
        ]:
            errors.append(
                "pubsub.delivery_guarantee must be one of: at_most_once, at_least_once, exactly_once"
            )

        # Validate security settings
        if self.security.max_messages_per_second < 1:
            errors.append("security.max_messages_per_second must be at least 1")

        # Validate logging settings
        valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.logging.level not in valid_log_levels:
            errors.append(f"logging.level must be one of: {', '.join(valid_log_levels)}")

        if errors:
            logger.error("config.validation_errors", errors=errors)

        return errors


# Global configuration instance
_config: PhoenixConfig | None = None


def get_config() -> PhoenixConfig:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = PhoenixConfig.from_env()
    return _config


def set_config(config: PhoenixConfig) -> None:
    """Set the global configuration instance."""
    global _config
    errors = config.validate()
    if errors:
        raise ValueError(f"Invalid configuration: {', '.join(errors)}")
    _config = config
    logger.info("config.updated", config=config.to_dict())
