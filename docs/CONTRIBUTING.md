# Contributing to Archon AI

First off, thank you for considering contributing to Archon AI! It's people like you that make Archon AI a great tool.

## Getting Started

1. **Fork the repository** on GitHub.
2. **Clone your fork** locally.
3. **Install dependencies**: `make install`.
4. **Create a branch** for your changes: `git checkout -b feature/my-new-feature`.
5. **Make your changes** and ensure tests pass: `make test`.
6. **Submit a Pull Request** to the `main` branch.

## Coding Standards

- **Linting**: We use **Ruff**. Run `make lint` before committing.
- **Formatting**: Run `make format` to auto-format your code.
- **Type Hints**: All new functions must have type hints.
- **Documentation**: Update the relevant documentation in the `docs/` directory.

## Pull Request Process

1. Ensure your code follows the existing style and patterns.
2. Include unit tests for new functionality.
3. If you're modifying the **Kernel**, a security review is mandatory. Please state clearly in your PR what security invariants you are preserving.
4. Update `CHANGELOG.md` (if available) or include a summary of changes in the PR description.

## Security Policy

Security is our top priority. If you discover a vulnerability:
- **Do NOT open a public issue.**
- Email the maintainers at security@archon.ai (placeholder).
- We aim to acknowledge reports within 24 hours and provide a fix within 7 days.

## Development Principles

1. **Safety First**: Progress is optional, safety is mandatory.
2. **Fail-Closed**: Any failure in validation must result in a DENY.
3. **Deterministic Kernel**: The Kernel should not rely on probabilistic models (LLMs).
4. **Audit Everything**: All actions must be logged in the tamper-evident audit log.
