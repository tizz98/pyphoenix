"""Exception classes for PyPhoenix."""


class PyPhoenixError(Exception):
    """Base exception class for PyPhoenix errors."""

    pass


class ChannelError(PyPhoenixError):
    """Exception raised for channel-related errors."""

    def __init__(self, message: str, channel_topic: str | None = None):
        super().__init__(message)
        self.channel_topic = channel_topic


class JoinError(ChannelError):
    """Exception raised when joining a channel fails."""

    pass


class PushError(ChannelError):
    """Exception raised when pushing a message fails."""

    pass


class ConnectionError(PyPhoenixError):
    """Exception raised for connection-related errors."""

    pass


class AuthenticationError(PyPhoenixError):
    """Exception raised for authentication failures."""

    pass


class AuthorizationError(PyPhoenixError):
    """Exception raised for authorization failures."""

    pass


class PresenceError(PyPhoenixError):
    """Exception raised for presence tracking errors."""

    pass


class PubSubError(PyPhoenixError):
    """Exception raised for PubSub system errors."""

    pass


class SerializationError(PyPhoenixError):
    """Exception raised for message serialization errors."""

    pass


class TimeoutError(PyPhoenixError):
    """Exception raised when operations timeout."""

    pass
