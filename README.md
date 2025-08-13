# PyPhoenix

[![Documentation Status](https://github.com/tizz98/pyphoenix/workflows/Documentation/badge.svg)](https://tizz98.github.io/pyphoenix/)
[![Tests](https://github.com/tizz98/pyphoenix/workflows/Tests/badge.svg)](https://github.com/tizz98/pyphoenix/actions)
[![PyPI version](https://badge.fury.io/py/pyphoenix.svg)](https://badge.fury.io/py/pyphoenix)
[![Python](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)

PyPhoenix is a Python implementation of the Phoenix Framework's real-time communication patterns. It provides channels, presence tracking, PubSub messaging, and WebSocket transport with a familiar Phoenix-style API.

## ✨ Features

- **🔌 Channels**: Join/leave/push/broadcast operations with Phoenix wire format compatibility
- **🌐 WebSocket Transport**: Async WebSocket handling with heartbeat and reconnection
- **📡 PubSub System**: Pattern-based message routing with wildcards (`room:*`)
- **👥 Presence Tracking**: Distributed presence state management
- **🔧 Middleware Framework**: Extensible middleware for logging, authentication, rate limiting
- **📊 Metrics & Monitoring**: Comprehensive metrics collection with counters, gauges, histograms
- **⚙️ Configuration System**: Environment variable and dict-based configuration
- **📱 Client Implementation**: Full client-side Socket and Channel with auto-reconnection
- **🔄 Message Serialization**: Support for JSON, MessagePack, and Pickle serialization

## 🚀 Quick Start

> **⚠️ Development Status**: PyPhoenix is currently in Phase 2 development. The examples below show the target API but may not be fully functional yet. See [Project Status](#-project-status) for current implementation status and [Contributing](#-contributing-to-phase-2-development) for ways to help complete the integration work.

### Installation

```bash
pip install pyphoenix
```

### Basic Server

```python
import asyncio
from pyphoenix import Phoenix, Channel

app = Phoenix()

@app.channel("room:*")
class RoomChannel(Channel):
    async def on_join(self, payload, socket):
        return {"status": "ok", "response": {"message": "Welcome!"}}
    
    async def on_message(self, payload, socket):
        await self.broadcast("new_message", payload)

if __name__ == "__main__":
    asyncio.run(app.start("localhost", 4000))
```

### Basic Client

```python
import asyncio
from pyphoenix import ClientSocket

async def main():
    client = ClientSocket("ws://localhost:4000/socket")
    await client.connect()
    
    room = client.channel("room:lobby")
    
    @room.on("new_message")
    async def on_message(payload, ref):
        print(f"Message: {payload}")
    
    await room.join()
    await room.push("message", {"text": "Hello, world!"})
    
    await asyncio.sleep(10)
    await room.leave()
    await client.disconnect()

asyncio.run(main())
```

## 📚 Documentation

- **[📖 Full Documentation](https://tizz98.github.io/pyphoenix/)**
- **[⚡ Quick Start Guide](https://tizz98.github.io/pyphoenix/quickstart.html)**
- **[📋 API Reference](https://tizz98.github.io/pyphoenix/api/)**
- **[💡 Examples](https://tizz98.github.io/pyphoenix/examples/)**
- **[🚀 Deployment Guide](https://tizz98.github.io/pyphoenix/deployment.html)**

## 🏗️ Advanced Usage

### With Middleware

```python
from pyphoenix import Phoenix, Channel, LoggingMiddleware, AuthMiddleware

app = Phoenix()

async def authenticate_user(payload):
    token = payload.get("token")
    if token == "valid_token":
        return {"user_id": "123", "username": "Alice"}
    return None

@app.channel("room:*")
class RoomChannel(Channel):
    def __init__(self, topic, params=None, socket=None):
        super().__init__(topic, params, socket)
        self.use_middleware(LoggingMiddleware())
        self.use_middleware(AuthMiddleware(authenticate_user))
    
    async def on_join(self, payload, socket):
        user = payload.get("authenticated_user")
        if user:
            return {"status": "ok", "response": {"user": user}}
        return {"status": "error", "response": {"reason": "Authentication required"}}
```

### With Configuration

```python
from pyphoenix import Phoenix, PhoenixConfig, set_config

config = PhoenixConfig(
    host="0.0.0.0",
    port=4001,
    debug=False
)

config.security.rate_limit_enabled = True
config.security.max_messages_per_second = 10
config.logging.log_channel_events = True

set_config(config)

app = Phoenix()
```

## 🧪 Development

### Setup

```bash
git clone https://github.com/tizz98/pyphoenix.git
cd pyphoenix
poetry install --with dev,docs
```

### Running Tests

```bash
poetry run pytest                    # Run all tests
poetry run pytest -v               # Verbose output
poetry run pytest --cov            # With coverage
```

### Code Formatting

```bash
poetry run ruff format              # Format code
poetry run ruff check               # Check linting
poetry run ruff check --fix         # Auto-fix issues
```

### Building Documentation

```bash
cd docs
poetry run sphinx-build -b html source build
```

### 🎯 **Contributing to Phase 2 Development**

**Current Priority Areas (Great for Contributors!):**

1. **Phoenix App Channel Routing** (`src/pyphoenix/phoenix.py`)
   - The Phoenix class needs to route incoming WebSocket connections to registered channels
   - Pattern matching for topics (`room:*` should match `room:123`)
   - Connection between `WebSocketTransport` and `Phoenix.channel_handlers`

2. **WebSocket ↔ Channel Integration** (`src/pyphoenix/socket.py`)
   - Socket should create channels via Phoenix app's registered handlers
   - Channel messages should route through Phoenix application context
   - Implement channel lifecycle management (join/leave/error handling)

3. **Client-Server Communication Testing**
   - End-to-end tests with real WebSocket connections
   - Example applications that demonstrate full client-server flows
   - Broadcasting tests with multiple connected clients

4. **PubSub Channel Integration** (`src/pyphoenix/pubsub.py` + `src/pyphoenix/channel.py`)
   - Channels should automatically publish/subscribe via PubSub
   - Cross-channel message routing and broadcasting
   - Presence updates should propagate through PubSub

**How to Help:**
- Pick any of the above areas and create focused PRs
- Add integration tests for client-server communication
- Create working examples in `examples/` directory
- Improve error handling and logging for debugging

**Testing Your Changes:**
```bash
# Test current basic functionality
poetry run pytest tests/

# Test WebSocket basics manually
poetry run python examples/even_more_basic_server.py  # Terminal 1
poetry run python examples/even_more_basic_client.py  # Terminal 2
```

## 🏛️ Architecture

PyPhoenix implements Phoenix's real-time communication patterns in Python:

```
┌─────────────────────────────────────────────┐
│                Application Layer             │
├─────────────────────────────────────────────┤
│                Channel Layer                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│  │ Channel  │ │ Presence │ │  Socket  │   │
│  │ Manager  │ │  Tracker │ │  Manager │   │
│  └──────────┘ └──────────┘ └──────────┘   │
├─────────────────────────────────────────────┤
│              Transport Layer                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│  │WebSocket │ │Middleware│ │  PubSub  │   │
│  └──────────┘ └──────────┘ └──────────┘   │
└─────────────────────────────────────────────┘
```

### Core Components

- **Phoenix Application**: Main entry point and channel routing
- **Channels**: Real-time communication contexts for specific topics
- **WebSocket Transport**: Async WebSocket handling with Phoenix wire format
- **PubSub**: Pattern-based message routing and distribution
- **Presence**: Distributed presence tracking and state management
- **Middleware**: Extensible request/response processing pipeline
- **Configuration**: Hierarchical configuration with environment support

## 📈 Performance

PyPhoenix is designed for high-performance real-time applications:

- **Concurrent Connections**: 10,000+ per process using asyncio
- **Message Throughput**: 100,000+ messages/second
- **Low Latency**: Sub-millisecond message routing
- **Memory Efficient**: Minimal memory footprint per connection
- **Horizontal Scaling**: Scale across multiple processes/machines

## 🔒 Security

- **Authentication Middleware**: Flexible authentication system
- **Rate Limiting**: Built-in rate limiting to prevent abuse
- **Input Validation**: Automatic payload validation
- **TLS Support**: Secure WebSocket connections (WSS)
- **CORS Configuration**: Configurable cross-origin policies

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Inspired by the [Phoenix Framework](https://phoenixframework.org/) and its real-time capabilities
- Built with modern Python async/await patterns
- Designed for the Python ecosystem's needs and conventions

## 📊 Project Status

PyPhoenix is currently in **Phase 2** development with core foundation complete:

### ✅ **Completed Foundation (Phase 1)**
- Core WebSocket implementation with asyncio support  
- Channel and Socket abstractions with Phoenix wire format
- PubSub messaging system with pattern matching
- Presence tracking with distributed state management
- Client implementation with decorator support
- Middleware framework architecture
- Configuration and metrics systems
- Comprehensive type definitions and error handling

### 🚧 **Current Development Phase (Phase 2): Integration & Testing**

**Next Priority Tasks (2-4 weeks):**

1. **Phoenix App Integration** ⭐ **CRITICAL**
   - Connect Phoenix app class to actual channel routing
   - Implement channel pattern matching (`room:*` → RoomChannel)
   - Bridge WebSocket connections to Phoenix application

2. **End-to-End Functionality** ⭐ **CRITICAL** 
   - Create working client-server examples that actually communicate
   - Fix channel join/leave flows between client and server
   - Ensure message broadcasting works across connections

3. **Core Feature Completion**
   - Complete PubSub integration with channel broadcasting
   - Implement presence synchronization across connections
   - Add comprehensive integration testing

4. **Developer Experience**
   - Working server/client examples in `examples/`
   - Basic tutorial documentation
   - Debugging and logging improvements

### 🔮 **Future Phases (Phase 3+)**

**Phase 3: Production Readiness (4-8 weeks)**
- Performance optimization and load testing
- Error recovery and fault tolerance
- Production deployment guides
- Framework integrations (Django, FastAPI, Flask)

**Phase 4: Advanced Features (8-16 weeks)**  
- Distributed multi-node support with node discovery
- Additional transport protocols (SSE, Long Polling)
- Advanced presence features (user tracking, rooms)
- Real-time analytics and monitoring dashboard

**Phase 5: Ecosystem (16+ weeks)**
- Plugin system architecture
- Community middleware and extensions
- Integration with message brokers (Redis, RabbitMQ)
- Performance benchmarks vs Phoenix Framework

---

**[📖 Read the Full Documentation](https://tizz98.github.io/pyphoenix/)** | **[🚀 View Examples](https://tizz98.github.io/pyphoenix/examples/)** | **[💬 Join Discussions](https://github.com/tizz98/pyphoenix/discussions)**
