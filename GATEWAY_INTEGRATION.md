# Archon AI + OpenClaw Gateway Integration Guide

## Quick Start (5 minutes)

### 1. Setup OpenClaw Gateway

```powershell
# Clone your fork (already done)
cd claw

# Install dependencies
pnpm install

# Start Gateway
pnpm gateway:dev
```

Gateway будет доступен по адресу: `ws://localhost:18789`

### 2. Test Connection

```powershell
# В новом терминале
cd ..  # вернуться в archon_ai
python test_gateway.py
```

Ожидаемый вывод:
```
============================================================
OpenClaw Gateway Integration Test
============================================================
Connecting to Gateway at ws://localhost:18789...
✅ Connected!
   Protocol version: 3
   Device token: eyJhbGciOiJIUzI1NiIs...
Listening for messages (5 seconds)...
Messages received: 0
Disconnected.
```

### 3. Настройка Telegram канала (опционально)

1. Создайте бота через @BotFather в Telegram
2. Получите токен
3. Настройте Gateway:

```json5
// claw/config/default.json5
{
  channels: {
    telegram: {
      enabled: true,
      botToken: "YOUR_BOT_TOKEN",
      dmPolicy: "pairing",
    },
  },
}
```

### 4. Тест с реальными сообщениями

```powershell
python test_real_messages.py
```

Отправьте сообщение вашему боту в Telegram — вы увидите его в консоли Archon AI.

## End-to-End Test

Полный тест с интерактивным меню:

```powershell
python test_end_to_end.py --interactive
```

Опции:
- Отправить тестовое сообщение через CLI
- Ждать реальных сообщений из Telegram/WhatsApp
- Просмотр статистики

## Docker Full Stack

Запуск Archon AI + Gateway в Docker:

```powershell
# Создайте .env файл
cat > .env << EOF
TELEGRAM_BOT_TOKEN=your_token_here
OPENAI_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here
EOF

# Запустить полный стек
make fullstack-up

# Проверить статус
curl http://localhost:8000/health
```

## Архитектура Integration

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           USER MESSAGE                                  │
│                    (Telegram/WhatsApp/Slack/etc.)                       │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      OPENCLAW GATEWAY (claw/)                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                  │
│  │   Telegram   │  │   WhatsApp   │  │    Slack     │  Channels        │
│  └──────────────┘  └──────────────┘  └──────────────┘                  │
│                                                                         │
│  ┌────────────────────────────────────────────────────────────────┐   │
│  │                    WebSocket Server (18789)                    │   │
│  │                    Protocol v3 (handshake)                     │   │
│  └─────────────────────────────────┬──────────────────────────────┘   │
└────────────────────────────────────┼────────────────────────────────────┘
                                     │ ws://localhost:18789
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        ARCHON AI (archon_ai/)                           │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    GatewayClientV3                              │   │
│  │              - Protocol v3 handshake                            │   │
│  │              - Heartbeat (tick)                                 │   │
│  │              - Auto-reconnect                                   │   │
│  └─────────────────────────────────┬───────────────────────────────┘   │
│                                    │                                    │
│                                    ▼                                    │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                 SecureGatewayBridge                             │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │   │
│  │  │    RBAC     │→│   Circuit   │→│   Execution Kernel      │ │   │
│  │  │   Check     │  │  Breaker    │  │  - Intent Contracts     │ │   │
│  │  └─────────────┘  └─────────────┘  │  - Invariants           │ │   │
│  │                                     │  - Validation           │ │   │
│  │  ┌──────────────────────────────────────────────────────────┐│   │
│  │  │              MAT (Multi-Agent Team)                      ││   │
│  │  │  - Debate Pipeline (GPT vs Claude vs Llama)             ││   │
│  │  │  - Code Review                                         ││   │
│  │  └──────────────────────────────────────────────────────────┘│   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Protocol v3 Handshake

```
Client                              Gateway
   │                                   │
   │◄──────── connect.challenge ──────┤
   │        {nonce, ts}                │
   │                                   │
   ├────────── connect ──────────────►│
   │  {role, scopes, client, device}  │
   │                                   │
   │◄────────── hello-ok ─────────────┤
   │    {protocol, deviceToken}        │
   │                                   │
   │◄════════ tick (every 15s) ══════►│
   │                                   │
   │◄════════ messages/events ═══════►│
```

## API Reference

### GatewayClientV3

```python
from openclaw import GatewayClientV3, GatewayConfig

config = GatewayConfig(
    url="ws://localhost:18789",
    client_id="my-client",
    role="operator",  # or "node", "bridge"
    scopes=["operator.read", "operator.write"]
)

client = GatewayClientV3(config)

# Event handlers
client.on_event("message", lambda msg: print(msg.payload))
client.on_event("agent.start", on_agent_start)

# Connect
await client.connect()

# Disconnect
await client.disconnect()
```

### SecureGatewayBridge

```python
from kernel import create_secure_bridge, IntegrationConfig

config = IntegrationConfig(
    ws_url="ws://localhost:18789",
    enable_circuit_breaker=True,
    enable_kernel_validation=True,
    enable_rbac=True
)

bridge = create_secure_bridge(config)

# Register message handler
bridge.register_secure_handler(
    pattern="deploy",
    handler=handle_deploy,
    operation_name="deploy_handler"
)

# Connect with Protocol v3
await bridge.connect_gateway_v3()
```

## Troubleshooting

### Connection refused
```powershell
# Проверьте, что Gateway запущен
curl http://localhost:18789/health

# Или через WebSocket
cd claw && pnpm openclaw doctor
```

### Protocol mismatch
- Gateway должен отправить `connect.challenge` перед handshake
- Проверьте версию Gateway: должна поддерживать protocol v3

### Authentication failed
- Убедитесь, что `role` и `scopes` правильные
- Для production настройте device fingerprint

### Сообщения не приходят
- Проверьте, что канал настроен (Telegram bot token)
- Убедитесь, что пользователь прошёл pairing (в Telegram)
- Проверьте логи Gateway: `cd claw && pnpm gateway:dev --verbose`

## Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `OPENCLAW_GATEWAY_URL` | Gateway WebSocket URL | `ws://localhost:18789` |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot API token | `123:abc...` |
| `WHATSAPP_SESSION` | WhatsApp Baileys session | `...` |
| `OPENAI_API_KEY` | OpenAI API key | `sk-...` |
| `ANTHROPIC_API_KEY` | Anthropic API key | `sk-ant-...` |

## Next Steps

1. **Добавьте свои обработчики** в `test_real_messages.py`
2. **Настройте Debate Pipeline** для сложных операций
3. **Включите Circuit Breaker** для production
4. **Добавьте инварианты безопасности** в Kernel
