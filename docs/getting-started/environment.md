# Environment Setup

Конфигурация переменных окружения для Archon AI.

---

## Quick Setup

```bash
# Copy template
cp .env.example .env

# Edit with your values
nano .env
```

---

## Required Variables

### LLM Providers

```bash
# OpenAI (required for GPT models)
OPENAI_API_KEY=sk-...

# Anthropic (required for Claude models)
ANTHROPIC_API_KEY=sk-ant-...

# Optional: Other providers
GOOGLE_API_KEY=...          # Gemini
GROQ_API_KEY=gsk_...        # Groq (FREE tier available)
XAI_API_KEY=...             # Grok
```

---

## Application Settings

```bash
# Server
API_HOST=0.0.0.0
API_PORT=8000
LOG_LEVEL=INFO

# Security
SECRET_KEY=changeme-change-me-in-production
CORS_ORIGINS=http://localhost:3000,http://localhost:8000
```

---

## Database (Optional)

```bash
# PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=archon_ai
POSTGRES_USER=archon
POSTGRES_PASSWORD=changeme

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
```

---

## Gateway Integration

```bash
# OpenClaw Gateway
OPENCLAW_GATEWAY_URL=ws://localhost:18789

# Telegram Bot
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...

# WhatsApp (optional)
WHATSAPP_SESSION=...
```

---

## Environment Profiles

### Development

```bash
ENVIRONMENT=dev
DEBUG=true
LOG_LEVEL=DEBUG
ENABLE_CORS=true
```

### Production

```bash
ENVIRONMENT=prod
DEBUG=false
LOG_LEVEL=INFO
ENABLE_CORS=false
SECRET_KEY=<strong-random-key>
```

### Testing

```bash
ENVIRONMENT=test
DEBUG=true
LOG_LEVEL=DEBUG
MOCK_LLM=true
```

---

## Using with Pydantic Settings

Configuration is managed via `enterprise/config.py`:

```python
from enterprise.config import settings

# Access settings
print(settings.app_name)
print(settings.database_url)
print(settings.is_production)
```

---

## Check Environment

```bash
# Verify all variables
make check-env

# Or manually
python check_env.py
```

---

## Security Notes

- **Never commit `.env` to version control**
- **Use strong `SECRET_KEY` in production**
- **Rotate API keys periodically**
- **Use environment-specific secrets in production**
