# Contributing to PyPhoenix

Thank you for your interest in contributing to PyPhoenix! This document provides guidelines and information for contributors.

## 🚀 Quick Start

1. Fork the repository on GitHub
2. Clone your fork locally:
   ```bash
   git clone https://github.com/your-username/pyphoenix.git
   cd pyphoenix
   ```
3. Install development dependencies:
   ```bash
   poetry install --with dev,docs
   ```
4. Create a feature branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```

## 🧪 Development Setup

### Prerequisites

- Python 3.13+
- Poetry for dependency management
- Git for version control

### Installation

```bash
# Clone the repository
git clone https://github.com/tizz98/pyphoenix.git
cd pyphoenix

# Install dependencies
poetry install --with dev,docs

# Activate the virtual environment
poetry shell
```

### Running Tests

```bash
# Run all tests
poetry run pytest

# Run tests with coverage
poetry run pytest --cov=pyphoenix --cov-report=html

# Run specific test file
poetry run pytest tests/test_channel.py

# Run tests with verbose output
poetry run pytest -v
```

### Code Quality

We use several tools to maintain code quality:

```bash
# Format code with ruff
poetry run ruff format

# Lint code with ruff
poetry run ruff check

# Fix auto-fixable lint issues
poetry run ruff check --fix

# Type checking (if mypy is added)
poetry run mypy src/pyphoenix
```

### Building Documentation

```bash
# Build documentation
cd docs
poetry run sphinx-build -b html source build

# Serve documentation locally
python -m http.server 8000 --directory build
```

## 📝 Coding Standards

### Code Style

- Follow PEP 8 style guidelines
- Use ruff for formatting (100 character line length)
- Add type hints to all public functions and methods
- Use descriptive variable and function names

### Documentation

- Add docstrings to all public classes and methods
- Use Google-style docstrings
- Include examples in docstrings when helpful
- Update documentation when adding new features

### Example Docstring

```python
async def join(self, params: dict[str, Any] | None = None) -> JoinResponse:
    """
    Join the channel and start receiving messages.

    This method initiates the channel join process. If middleware is configured,
    it will be executed before the final join handler.

    Args:
        params: Optional parameters to send with join request.
               These are merged with the channel's initial params.

    Returns:
        JoinResponse: An object containing the join status and response data.

    Raises:
        JoinError: If the join operation fails
        TimeoutError: If the join times out

    Example:
        Basic join::

            response = await channel.join({"user_id": "123"})
            if response.status == "ok":
                print("Successfully joined channel!")
    """
```

## 🐛 Bug Reports

When filing bug reports, please include:

1. **Clear description** of the issue
2. **Steps to reproduce** the bug
3. **Expected behavior** vs actual behavior
4. **Environment information**:
   - Python version
   - PyPhoenix version
   - Operating system
   - Relevant dependencies
5. **Code samples** that demonstrate the issue
6. **Error messages** and stack traces

## ✨ Feature Requests

For feature requests, please provide:

1. **Clear description** of the proposed feature
2. **Use case** and motivation
3. **Proposed API** or interface (if applicable)
4. **Implementation considerations**
5. **Backward compatibility** impact

## 🔧 Pull Request Process

### Before Submitting

1. **Create an issue** first to discuss the change (for significant features)
2. **Fork the repository** and create a feature branch
3. **Write tests** for your changes
4. **Update documentation** as needed
5. **Follow coding standards** and style guidelines

### Submitting

1. **Run tests** and ensure they pass:
   ```bash
   poetry run pytest
   ```

2. **Run code quality checks**:
   ```bash
   poetry run ruff format
   poetry run ruff check
   ```

3. **Build documentation** and verify it looks correct:
   ```bash
   poetry run sphinx-build -b html docs/source docs/build
   ```

4. **Write clear commit messages**:
   ```
   feat: add rate limiting middleware
   
   - Implement RateLimitMiddleware with configurable limits
   - Add tests for rate limiting functionality
   - Update documentation with usage examples
   
   Fixes #123
   ```

5. **Create pull request** with:
   - Clear title and description
   - Reference to related issues
   - Summary of changes
   - Testing notes

### Review Process

1. **Automated checks** must pass (tests, linting, documentation build)
2. **Code review** by maintainers
3. **Feedback incorporation** if needed
4. **Final approval** and merge

## 📚 Project Structure

```
pyphoenix/
├── src/pyphoenix/          # Main package source
│   ├── __init__.py         # Package exports
│   ├── channel.py          # Channel implementation
│   ├── phoenix.py          # Main application class
│   ├── pubsub.py          # PubSub system
│   ├── presence.py        # Presence tracking
│   ├── socket.py          # WebSocket transport
│   ├── client.py          # Client implementation
│   ├── middleware.py      # Middleware framework
│   ├── config.py          # Configuration system
│   ├── metrics.py         # Metrics collection
│   ├── serializers.py     # Message serialization
│   ├── exceptions.py      # Custom exceptions
│   ├── types.py           # Type definitions
│   └── message_queue.py   # Message queuing
├── tests/                 # Test suite
├── docs/                  # Documentation
├── examples/              # Example applications
├── .github/               # GitHub workflows
└── pyproject.toml         # Project configuration
```

## 🏷️ Release Process

### Version Numbering

We follow [Semantic Versioning](https://semver.org/):

- **MAJOR**: Incompatible API changes
- **MINOR**: New functionality (backward compatible)
- **PATCH**: Bug fixes (backward compatible)

### Release Steps

1. Update version in `pyproject.toml`
2. Update `CHANGELOG.md` with release notes
3. Create release PR and get approval
4. Tag release: `git tag v0.1.0`
5. Push tag: `git push origin v0.1.0`
6. GitHub Actions will handle PyPI publishing

## 📋 Testing Guidelines

### Test Organization

- Unit tests for individual components
- Integration tests for component interaction
- End-to-end tests for complete workflows
- Performance tests for critical paths

### Test Naming

```python
class TestChannel:
    def test_channel_creation(self):
        """Test basic channel creation."""
        
    async def test_join_success(self):
        """Test successful channel join."""
        
    async def test_join_with_authentication_failure(self):
        """Test join failure with invalid authentication."""
```

### Test Coverage

- Aim for 90%+ test coverage
- Test both success and failure paths
- Include edge cases and error conditions
- Mock external dependencies appropriately

## 🤝 Code of Conduct

### Our Pledge

We are committed to providing a friendly, safe, and welcoming environment for all contributors, regardless of experience level, gender identity and expression, sexual orientation, disability, personal appearance, body size, race, ethnicity, age, religion, nationality, or other similar characteristics.

### Expected Behavior

- Be respectful and inclusive
- Exercise empathy and kindness
- Focus on what is best for the community
- Accept constructive criticism gracefully
- Show courtesy and respect towards other community members

### Unacceptable Behavior

- Harassment, discrimination, or intimidation
- Offensive comments or personal attacks
- Public or private harassment
- Publishing others' private information without permission
- Conduct that could reasonably be considered inappropriate

## 📞 Getting Help

- **Documentation**: https://tizz98.github.io/pyphoenix/
- **Issues**: https://github.com/tizz98/pyphoenix/issues
- **Discussions**: https://github.com/tizz98/pyphoenix/discussions
- **Email**: dev.tizz98@gmail.com

## 🏆 Recognition

Contributors will be recognized in:

- Release notes for significant contributions
- Contributors section in documentation
- Special thanks in the README

Thank you for contributing to PyPhoenix! 🎉