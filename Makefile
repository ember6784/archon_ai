# Archon AI - Makefile
# ====================

.PHONY: help install run test docker-build docker-up docker-down docker-logs clean lint format gateway-dev gateway-test gateway-e2e quant-setup quant-run quant-test fullstack-up fullstack-down

# Default target
help:
	@echo "Archon AI - Available commands:"
	@echo ""
	@echo "Development:"
	@echo "  make install         - Install dependencies"
	@echo "  make run             - Run API server locally"
	@echo "  make test            - Run tests"
	@echo "  make lint            - Run linting"
	@echo "  make format          - Format code"
	@echo ""
	@echo "Gateway (OpenClaw):"
	@echo "  make gateway-dev     - Run Gateway locally (requires claw/)"
	@echo "  make gateway-test    - Test Gateway connection"
	@echo "  make gateway-e2e     - Run E2E test"
	@echo "  make fullstack-up    - Start Archon AI + Gateway (Docker)"
	@echo "  make fullstack-down  - Stop full stack"
	@echo ""
	@echo "@quant_dev_ai_bot:"
	@echo "  make quant-setup     - Setup bot configuration"
	@echo "  make quant-run       - Run with bot"
	@echo "  make quant-test      - Test bot connection"
	@echo ""
	@echo "Environment (.env):"
	@echo "  make check-env       - Check environment variables"
	@echo "  make setup-env       - Setup from .env file"
	@echo "  make run-bot         - Start bot integration"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build    - Build Docker images"
	@echo "  make docker-up       - Start services (docker-compose)"
	@echo "  make docker-down     - Stop services"
	@echo "  make docker-logs     - View logs"
	@echo "  make docker-dev      - Start development environment"
	@echo ""
	@echo "Utilities:"
	@echo "  make clean           - Clean temporary files"
	@echo "  make health          - Check API health"
	@echo "  make docs            - Open API documentation"

# Install dependencies
install:
	pip install fastapi uvicorn anthropic openai aiohttp
	pip install pytest pytest-asyncio pytest-cov httpx
	pip install black ruff mypy

# Run API server locally
run:
	uvicorn enterprise.api.main:app --reload --host 0.0.0.0 --port 8000

# Run tests
test:
	python -m pytest tests/ -v --cov=enterprise --cov=mat --cov-report=term-missing

# Run linting
lint:
	ruff check mat/ enterprise/ tests/
	mypy mat/ enterprise/

# Format code
format:
	ruff check --fix mat/ enterprise/ tests/
	black mat/ enterprise/ tests/

# Gateway (OpenClaw) development
gateway-dev:
	@echo "Starting OpenClaw Gateway..."
	@echo "Make sure you have claw/ directory with Gateway installed"
	cd claw && pnpm gateway:dev

gateway-test:
	@echo "Testing Gateway connection..."
	python test_gateway.py

gateway-e2e:
	@echo "Running end-to-end test..."
	python test_end_to_end.py --interactive

# @quant_dev_ai_bot integration
quant-setup:
	@echo "Setting up @quant_dev_ai_bot..."
	python setup_quant_bot.py

quant-run:
	@echo "Running Archon AI with @quant_dev_ai_bot..."
	python run_quant_bot.py

quant-test:
	@echo "Testing bot connection..."
	python test_gateway.py

# Environment setup from .env
check-env:
	@echo "Checking environment..."
	python check_env.py

setup-env:
	@echo "Setting up from .env..."
	python setup_from_env.py

run-bot:
	@echo "Starting bot integration..."
	python run_quant_bot.py

# Full stack (Archon AI + Gateway)
fullstack-up:
	docker-compose -f docker-compose.fullstack.yml up -d
	@echo "Full stack starting..."
	@echo "Gateway: ws://localhost:18789"
	@echo "API: http://localhost:8000"
	@sleep 5
	@make health

fullstack-down:
	docker-compose -f docker-compose.fullstack.yml down

# Docker build
docker-build:
	docker-compose build

# Docker up
docker-up:
	docker-compose up -d
	@echo "Waiting for services to start..."
	@sleep 5
	@make health

# Docker down
docker-down:
	docker-compose down

# Docker logs
docker-logs:
	docker-compose logs -f archon-api

# Development environment
docker-dev:
	docker-compose -f docker-compose.dev.yml up -d
	@echo "Development environment started"
	@echo "API: http://localhost:8000"
	@echo "pgAdmin: http://localhost:5050 (tools profile)"

# Clean temporary files
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.coverage" -delete
	find . -type f -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true

# Health check
health:
	@echo "Checking API health..."
	@curl -s http://localhost:8000/health | python -m json.tool || echo "API not responding"

# Open documentation
docs:
	@echo "Opening API documentation..."
	@echo "Swagger UI: http://localhost:8000/docs"
	@echo "ReDoc: http://localhost:8000/redoc"
	@if command -v xdg-open >/dev/null 2>&1; then \
		xdg-open http://localhost:8000/docs; \
	elif command -v open >/dev/null 2>&1; then \
		open http://localhost:8000/docs; \
	else \
		echo "Please open http://localhost:8000/docs in your browser"; \
	fi
