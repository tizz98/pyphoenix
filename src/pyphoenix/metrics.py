"""Metrics and monitoring system for PyPhoenix."""

import asyncio
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class MetricValue:
    """A metric value with timestamp."""

    value: float
    timestamp: float
    labels: dict[str, str] = field(default_factory=dict)


class Counter:
    """Thread-safe counter metric."""

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self._value = 0.0
        self._lock = asyncio.Lock()

    async def inc(self, amount: float = 1.0, labels: dict[str, str] | None = None) -> None:
        """Increment the counter."""
        async with self._lock:
            self._value += amount

    async def get(self) -> float:
        """Get the current counter value."""
        async with self._lock:
            return self._value

    async def reset(self) -> None:
        """Reset the counter to zero."""
        async with self._lock:
            self._value = 0.0


class Gauge:
    """Thread-safe gauge metric."""

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self._value = 0.0
        self._lock = asyncio.Lock()

    async def set(self, value: float, labels: dict[str, str] | None = None) -> None:
        """Set the gauge value."""
        async with self._lock:
            self._value = value

    async def inc(self, amount: float = 1.0, labels: dict[str, str] | None = None) -> None:
        """Increment the gauge."""
        async with self._lock:
            self._value += amount

    async def dec(self, amount: float = 1.0, labels: dict[str, str] | None = None) -> None:
        """Decrement the gauge."""
        async with self._lock:
            self._value -= amount

    async def get(self) -> float:
        """Get the current gauge value."""
        async with self._lock:
            return self._value


class Histogram:
    """Thread-safe histogram metric."""

    def __init__(self, name: str, description: str = "", buckets: list[float] | None = None):
        self.name = name
        self.description = description
        self.buckets = buckets or [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
        self._observations: deque[float] = deque(maxlen=10000)  # Keep last 10k observations
        self._bucket_counts = dict.fromkeys(self.buckets, 0)
        self._bucket_counts[float("inf")] = 0
        self._sum = 0.0
        self._count = 0
        self._lock = asyncio.Lock()

    async def observe(self, value: float, labels: dict[str, str] | None = None) -> None:
        """Observe a value."""
        async with self._lock:
            self._observations.append(value)
            self._sum += value
            self._count += 1

            # Update bucket counts
            for bucket in self.buckets:
                if value <= bucket:
                    self._bucket_counts[bucket] += 1
            self._bucket_counts[float("inf")] += 1

    async def get_stats(self) -> dict[str, Any]:
        """Get histogram statistics."""
        async with self._lock:
            if not self._observations:
                return {
                    "count": 0,
                    "sum": 0.0,
                    "avg": 0.0,
                    "min": 0.0,
                    "max": 0.0,
                    "p50": 0.0,
                    "p95": 0.0,
                    "p99": 0.0,
                    "buckets": dict(self._bucket_counts),
                }

            sorted_obs = sorted(self._observations)

            return {
                "count": self._count,
                "sum": self._sum,
                "avg": self._sum / self._count if self._count > 0 else 0.0,
                "min": sorted_obs[0],
                "max": sorted_obs[-1],
                "p50": self._percentile(sorted_obs, 0.5),
                "p95": self._percentile(sorted_obs, 0.95),
                "p99": self._percentile(sorted_obs, 0.99),
                "buckets": dict(self._bucket_counts),
            }

    def _percentile(self, sorted_values: list[float], p: float) -> float:
        """Calculate percentile from sorted values."""
        if not sorted_values:
            return 0.0

        index = int(p * (len(sorted_values) - 1))
        return sorted_values[index]


class MetricsRegistry:
    """Registry for managing metrics."""

    def __init__(self):
        self.counters: dict[str, Counter] = {}
        self.gauges: dict[str, Gauge] = {}
        self.histograms: dict[str, Histogram] = {}
        self._lock = asyncio.Lock()

    async def counter(self, name: str, description: str = "") -> Counter:
        """Get or create a counter metric."""
        async with self._lock:
            if name not in self.counters:
                self.counters[name] = Counter(name, description)
            return self.counters[name]

    async def gauge(self, name: str, description: str = "") -> Gauge:
        """Get or create a gauge metric."""
        async with self._lock:
            if name not in self.gauges:
                self.gauges[name] = Gauge(name, description)
            return self.gauges[name]

    async def histogram(
        self, name: str, description: str = "", buckets: list[float] | None = None
    ) -> Histogram:
        """Get or create a histogram metric."""
        async with self._lock:
            if name not in self.histograms:
                self.histograms[name] = Histogram(name, description, buckets)
            return self.histograms[name]

    async def get_all_metrics(self) -> dict[str, Any]:
        """Get all metrics and their values."""
        metrics = {"counters": {}, "gauges": {}, "histograms": {}}

        # Get counter values
        for name, counter in self.counters.items():
            metrics["counters"][name] = await counter.get()

        # Get gauge values
        for name, gauge in self.gauges.items():
            metrics["gauges"][name] = await gauge.get()

        # Get histogram statistics
        for name, histogram in self.histograms.items():
            metrics["histograms"][name] = await histogram.get_stats()

        return metrics

    async def clear(self) -> None:
        """Clear all metrics."""
        async with self._lock:
            for counter in self.counters.values():
                await counter.reset()

            self.counters.clear()
            self.gauges.clear()
            self.histograms.clear()


class PhoenixMetrics:
    """Phoenix-specific metrics collector."""

    def __init__(self, registry: MetricsRegistry):
        self.registry = registry
        self._setup_metrics()

    def _setup_metrics(self) -> None:
        """Set up Phoenix-specific metrics."""
        # This is done synchronously as they are just metric definitions
        pass

    async def record_connection(self, transport: str = "websocket") -> None:
        """Record a new connection."""
        connections_total = await self.registry.counter(
            "pyphoenix_connections_total", "Total number of connections"
        )
        await connections_total.inc(labels={"transport": transport})

        active_connections = await self.registry.gauge(
            "pyphoenix_active_connections", "Number of active connections"
        )
        await active_connections.inc(labels={"transport": transport})

    async def record_disconnection(self, transport: str = "websocket") -> None:
        """Record a disconnection."""
        active_connections = await self.registry.gauge(
            "pyphoenix_active_connections", "Number of active connections"
        )
        await active_connections.dec(labels={"transport": transport})

    async def record_channel_join(self, topic: str, success: bool = True) -> None:
        """Record a channel join attempt."""
        channel_joins = await self.registry.counter(
            "pyphoenix_channel_joins_total", "Total number of channel joins"
        )
        await channel_joins.inc(
            labels={"topic_pattern": self._topic_pattern(topic), "success": str(success)}
        )

        if success:
            active_channels = await self.registry.gauge(
                "pyphoenix_active_channels", "Number of active channels"
            )
            await active_channels.inc(labels={"topic_pattern": self._topic_pattern(topic)})

    async def record_channel_leave(self, topic: str) -> None:
        """Record a channel leave."""
        active_channels = await self.registry.gauge(
            "pyphoenix_active_channels", "Number of active channels"
        )
        await active_channels.dec(labels={"topic_pattern": self._topic_pattern(topic)})

    async def record_message_sent(self, topic: str, event: str) -> None:
        """Record a message sent."""
        messages_sent = await self.registry.counter(
            "pyphoenix_messages_sent_total", "Total number of messages sent"
        )
        await messages_sent.inc(
            labels={"topic_pattern": self._topic_pattern(topic), "event": event}
        )

    async def record_message_received(self, topic: str, event: str) -> None:
        """Record a message received."""
        messages_received = await self.registry.counter(
            "pyphoenix_messages_received_total", "Total number of messages received"
        )
        await messages_received.inc(
            labels={"topic_pattern": self._topic_pattern(topic), "event": event}
        )

    async def record_message_processing_time(self, topic: str, event: str, duration: float) -> None:
        """Record message processing time."""
        processing_time = await self.registry.histogram(
            "pyphoenix_message_processing_duration_seconds",
            "Time spent processing messages",
        )
        await processing_time.observe(
            duration, labels={"topic_pattern": self._topic_pattern(topic), "event": event}
        )

    async def record_presence_track(self, topic: str) -> None:
        """Record presence tracking."""
        presence_tracks = await self.registry.counter(
            "pyphoenix_presence_tracks_total", "Total number of presence tracks"
        )
        await presence_tracks.inc(labels={"topic_pattern": self._topic_pattern(topic)})

        active_presences = await self.registry.gauge(
            "pyphoenix_active_presences", "Number of active presences"
        )
        await active_presences.inc(labels={"topic_pattern": self._topic_pattern(topic)})

    async def record_presence_untrack(self, topic: str) -> None:
        """Record presence untracking."""
        active_presences = await self.registry.gauge(
            "pyphoenix_active_presences", "Number of active presences"
        )
        await active_presences.dec(labels={"topic_pattern": self._topic_pattern(topic)})

    async def record_pubsub_publish(self, topic: str, subscribers: int) -> None:
        """Record PubSub message publication."""
        pubsub_publishes = await self.registry.counter(
            "pyphoenix_pubsub_publishes_total", "Total number of PubSub publishes"
        )
        await pubsub_publishes.inc(labels={"topic_pattern": self._topic_pattern(topic)})

        pubsub_subscribers = await self.registry.histogram(
            "pyphoenix_pubsub_subscribers", "Number of subscribers per publish"
        )
        await pubsub_subscribers.observe(
            subscribers, labels={"topic_pattern": self._topic_pattern(topic)}
        )

    async def record_error(self, error_type: str, component: str) -> None:
        """Record an error."""
        errors = await self.registry.counter("pyphoenix_errors_total", "Total number of errors")
        await errors.inc(labels={"type": error_type, "component": component})

    def _topic_pattern(self, topic: str) -> str:
        """Extract topic pattern from specific topic."""
        parts = topic.split(":")
        if len(parts) >= 2:
            return f"{parts[0]}:*"
        return topic


class MetricsCollector:
    """Background metrics collector."""

    def __init__(self, registry: MetricsRegistry, collect_interval: float = 60.0):
        self.registry = registry
        self.collect_interval = collect_interval
        self.collectors: list[Callable[[], Any]] = []
        self.running = False
        self.task: asyncio.Task | None = None

    def add_collector(self, collector: Callable[[], Any]) -> None:
        """Add a metrics collector function."""
        self.collectors.append(collector)

    async def start(self) -> None:
        """Start the metrics collection loop."""
        if self.running:
            return

        self.running = True
        self.task = asyncio.create_task(self._collect_loop())
        logger.info("metrics_collector.started")

    async def stop(self) -> None:
        """Stop the metrics collection loop."""
        if not self.running:
            return

        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

        logger.info("metrics_collector.stopped")

    async def _collect_loop(self) -> None:
        """Main metrics collection loop."""
        while self.running:
            try:
                # Run all collectors
                for collector in self.collectors:
                    try:
                        if asyncio.iscoroutinefunction(collector):
                            await collector()
                        else:
                            collector()
                    except Exception as e:
                        logger.error("metrics_collector.collector_error", error=str(e))

                await asyncio.sleep(self.collect_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("metrics_collector.loop_error", error=str(e))
                await asyncio.sleep(1)  # Error recovery delay


# Global metrics registry and Phoenix metrics
_metrics_registry: MetricsRegistry | None = None
_phoenix_metrics: PhoenixMetrics | None = None


async def get_metrics_registry() -> MetricsRegistry:
    """Get the global metrics registry."""
    global _metrics_registry
    if _metrics_registry is None:
        _metrics_registry = MetricsRegistry()
    return _metrics_registry


async def get_phoenix_metrics() -> PhoenixMetrics:
    """Get the Phoenix metrics collector."""
    global _phoenix_metrics
    if _phoenix_metrics is None:
        registry = await get_metrics_registry()
        _phoenix_metrics = PhoenixMetrics(registry)
    return _phoenix_metrics
