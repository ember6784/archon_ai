# Commands Reference

Полный справочник команд для работы с Archon AI и OpenClaw Gateway.

---

## Quick Start (3 Commands)

```bash
# 1. Check environment
python check_env.py

# 2. Start Gateway (Terminal 1)
cd claw && pnpm gateway:dev

# 3. Start bot (Terminal 2)
python run_quant_bot.py
```

---

## OpenClaw Gateway

### Start Gateway

```bash
# Basic start
cd claw
pnpm gateway:dev

# Without auth (development)
node scripts/run-node.mjs gateway --allow-unconfigured --verbose

# Custom port
node scripts/run-node.mjs gateway --port 18789 --verbose

# WebSocket only (no channels)
OPENCLAW_SKIP_CHANNELS=1 node scripts/run-node.mjs gateway --verbose
```

### Stop Gateway

```bash
# Graceful stop
node openclaw.mjs gateway stop

# Force stop
node openclaw.mjs gateway stop --force

# Or via process
taskkill /PID <PID> /F  # Windows
kill -9 <PID>           # Linux/Mac
```

### Configuration

```bash
# Interactive setup
node openclaw.mjs onboard

# View config
node openclaw.mjs config

# Set value
node openclaw.mjs configure <key>=<value>

# Examples
node openclaw.mjs configure gateway.port=18789
node openclaw.mjs configure channels.telegram.enabled=true
```

### Health & Status

```bash
# Health check
curl http://localhost:18789/health

# Diagnostics
node openclaw.mjs doctor

# Status
node openclaw.mjs status
```

---

## Archon AI (Makefile)

### Development

| Command | Description |
|---------|-------------|
| `make install` | Install dependencies |
| `make run` | Start API server (with reload) |
| `make test` | Run all tests with coverage |
| `make lint` | Run ruff and mypy |
| `make format` | Auto-fix and format code |

### Gateway

| Command | Description |
|---------|-------------|
| `make gateway-dev` | Start Gateway via pnpm |
| `make gateway-test` | Test connection |
| `make gateway-e2e` | E2E test |

### Bot

| Command | Description |
|---------|-------------|
| `make quant-setup` | Setup bot |
| `make quant-run` | Run with bot |
| `make quant-test` | Test bot |
| `make run-bot` | Run bot integration |

### Environment

| Command | Description |
|---------|-------------|
| `make check-env` | Verify .env |
| `make setup-env` | Setup from .env |

### Docker

| Command | Description |
|---------|-------------|
| `make docker-build` | Build images |
| `make docker-up` | Start services |
| `make docker-down` | Stop services |
| `make docker-dev` | Dev environment |
| `make fullstack-up` | Full stack + Gateway |
| `make fullstack-down` | Stop stack |

---

## Python Scripts

```bash
# Environment check
python check_env.py

# Setup from .env
python setup_from_env.py

# Gateway tests
python test_gateway.py          # Basic test
python test_real_messages.py    # Real messages
python test_end_to_end.py --interactive  # E2E

# Run bot
python run_quant_bot.py
```

---

## API Endpoints

### Health

```bash
curl http://localhost:8000/health
```

### Circuit Breaker

```bash
# Get status
curl http://localhost:8000/api/v1/circuit_breaker/status

# Record human activity
curl -X POST http://localhost:8000/api/v1/circuit_breaker/record_activity \
  -H "Content-Type: application/json" \
  -d '{"action": "manual_review"}'
```

### Siege Mode

```bash
# Activate
curl -X POST http://localhost:8000/api/v1/siege/activate

# Deactivate
curl -X POST http://localhost:8000/api/v1/siege/deactivate
```

### Debate

```bash
curl -X POST http://localhost:8000/api/v1/debate/start \
  -H "Content-Type: application/json" \
  -d '{
    "code": "def add(a, b): return a + b",
    "requirements": "Create add function",
    "file_path": "math.py"
  }'
```

### RBAC

```bash
# List roles
curl http://localhost:8000/api/v1/rbac/roles

# Assign role
curl -X POST http://localhost:8000/api/v1/rbac/assign \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user123", "role": "operator"}'
```

### Audit

```bash
# Query events
curl "http://localhost:8000/api/v1/audit/events?limit=10"

# Verify chain
curl http://localhost:8000/api/v1/audit/verify
```

---

## Telegram Bot

### Pairing

```bash
# 1. Get code in Telegram: /start

# 2. Approve
cd claw
node openclaw.mjs pairing approve telegram <CODE>

# List pending
node openclaw.mjs pairing list

# Reject
node openclaw.mjs pairing reject telegram <CODE>
```

### Send Messages

```bash
# Via CLI
node openclaw.mjs message send --to <USER_ID> --message "Hello"

# Via agent
node openclaw.mjs agent --message "Your message" --to <USER_ID>
```

---

## Skills Management

```bash
# List available
node openclaw.mjs skills list

# Install skill
node openclaw.mjs skills install github
node openclaw.mjs skills install openai-image-gen
node openclaw.mjs skills install openai-whisper

# Install all
node openclaw.mjs skills install --all

# Update
node openclaw.mjs skills update

# Remove
node openclaw.mjs skills remove <skill-name>
```

---

## Docker

```bash
# Build
docker-compose build

# Start
docker-compose up -d

# Logs
docker-compose logs -f archon-api
docker-compose logs -f openclaw-gateway

# Full stack
docker-compose -f docker-compose.fullstack.yml up -d

# Stop
docker-compose down
docker-compose -f docker-compose.fullstack.yml down
```

---

## Troubleshooting

### Gateway Won't Start

```bash
# Check port
netstat -ano | findstr 18789  # Windows
lsof -i :18789               # Linux/Mac

# Kill process
taskkill /PID <PID> /F       # Windows
kill -9 <PID>                # Linux/Mac

# Try different port
node scripts/run-node.mjs gateway --port 18888
```

### Connection Issues

```bash
# Test WebSocket
curl -i -N -H "Connection: Upgrade" \
  -H "Upgrade: websocket" \
  -H "Host: localhost:18789" \
  -H "Origin: http://localhost" \
  http://localhost:18789

# View logs
cd claw && node openclaw.mjs logs

# Debug mode
node scripts/run-node.mjs gateway --verbose --debug
```

### Reset Configuration

```bash
# Reset Gateway
node openclaw.mjs gateway --reset

# Full reset
node openclaw.mjs reset

# Remove lock file
rm ~/.openclaw/gateway.lock
```

---

## Debug Commands

```bash
# Check imports
python check_imports.py

# Check environment
python check_env.py

# Test Gateway
python test_gateway.py

# Check API
curl http://localhost:8000/health | python -m json.tool
```

---

## Emergency Commands

Full system restart:

```bash
# 1. Stop everything
node openclaw.mjs gateway stop
pkill -f python
pkill -f node

# 2. Clean
make clean

# 3. Restart
# Terminal 1
cd claw && node scripts/run-node.mjs gateway --allow-unconfigured --verbose

# Terminal 2
python run_quant_bot.py
```

---

## Useful URLs

| Service | URL |
|---------|-----|
| Gateway Dashboard | http://localhost:18789/overview |
| API Docs | http://localhost:8000/docs |
| Telegram Bot | https://t.me/quant_dev_ai_bot |

---

## Shell Aliases (Optional)

Add to your shell profile:

```bash
# Archon AI
alias archon-start="cd ~/archon_ai && python run_quant_bot.py"
alias archon-check="cd ~/archon_ai && python check_env.py"
alias archon-api="cd ~/archon_ai && make run"

# Gateway
alias gateway-start="cd ~/archon_ai/claw && pnpm gateway:dev"
alias gateway-stop="cd ~/archon_ai/claw && node openclaw.mjs gateway stop"
alias gateway-logs="cd ~/archon_ai/claw && node openclaw.mjs logs"

# Docker
alias docker-fullstack="cd ~/archon_ai && make fullstack-up"
```
