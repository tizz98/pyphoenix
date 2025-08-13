# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

This project uses Poetry for dependency management and packaging:

- **Install dependencies**: `poetry install`
- **Run tests**: `poetry run pytest`
- **Code formatting**: `poetry run ruff format .`
- **Code linting**: `poetry run ruff check .`
- **Fix linting issues**: `poetry run ruff check --fix .`
- **Build package**: `poetry build`
- **Run Python scripts**: `poetry run python <script.py>`
- **Add dependencies**: `poetry add <package>`
- **Add dev dependencies**: `poetry add --group dev <package>`

## Project Architecture

PyPhoenix is a Python library designed to bring Elixir Phoenix-style real-time communication channels to Python applications. The project is in early development stage.

### Core Architecture Concepts

The library is designed around several key abstractions:

1. **Channels**: Primary abstraction for real-time communication representing conversations on specific topics
2. **Topics**: Hierarchical string identifiers for message routing (e.g., `"room:123"`, `"user:456:notifications"`)
3. **Presence**: Distributed presence tracking across multiple server nodes
4. **PubSub**: Internal publish-subscribe system for inter-process communication

### High-Level System Design

The architecture follows a layered approach:
- **Application Layer**: User-facing API and channel management
- **Channel Layer**: Channel Manager, Presence Tracker, Socket Manager
- **Transport Layer**: WebSocket (primary), Server-Sent Events (fallback), Long Polling (compatibility)
- **Distribution Layer**: PubSub Bus, CRDT Engine, Mesh Network

### Process Model

Unlike Elixir's BEAM VM, PyPhoenix uses:
- AsyncIO for concurrent I/O operations
- multiprocessing.Process for CPU-bound work isolation
- Threading for specific blocking operations
- Process pools for horizontal scaling

### Distribution Strategy

- **Node Discovery**: mDNS/Zeroconf for local networks, Gossip Protocol for WAN
- **State Synchronization**: CRDTs for eventually consistent state
- **Message Routing**: Ring-based consistent hashing for channel ownership

### Package Structure

- `src/pyphoenix/`: Main package source code
- `tests/`: Test files (currently minimal)

### Key Design Goals

1. Pure Python implementation without external dependencies like Redis
2. Horizontal scaling capability
3. Fault tolerance with supervisor trees and circuit breakers
4. Multiple transport protocols support
5. Developer-friendly API similar to Phoenix/Elixir patterns

### Current Development Stage

The project is currently in the design/planning phase with minimal implementation. The README.md serves as a comprehensive design document outlining the planned architecture and features across a 6+ month roadmap.

### Requirements

- Python 3.13+ (as specified in pyproject.toml)
- Poetry for development workflow
- Use ruff for code formatting with 100 character line length.
- Ensure new line at end of files.
