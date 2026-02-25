# OpenClaw Gateway Integration

Интеграция Archon AI с OpenClaw Gateway для приёма сообщений из Telegram, WhatsApp, Slack и других каналов.

---

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Telegram/     │     │  OpenClaw        │     │   Archon AI     │
│   WhatsApp/     │────▶│  Gateway         │────▶│   GatewayClient │
│   Slack         │     │  (Node.js)       │     │   V3            │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                              ws://localhost:18789        │
                                                          ▼
                                                   ┌─────────────────┐
                                                   │  SecureGateway  │
                                                   │  Bridge         │
                                                   └─────────────────┘
                                                          │
                           ┌──────────────────────────────┼──────────────┐
                           ▼                              ▼              ▼
                    ┌─────────────┐              ┌─────────────┐   ┌──────────┐
                    │  Execution  │              │   MAT/      │   │ Circuit  │
                    │  Kernel     │              │   Debates   │   │ Breaker  │
                    └─────────────┘              └─────────────┘   └──────────┘
```

---

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

---

## API Reference

### GatewayClientV3

```python
from openclaw import GatewayClientV3, GatewayConfig

config = GatewayConfig(
    url="ws://localhost:18789",
    client_id="my-client",
    role="operator",  # or "node", "bridge"
    scopes=["operator.read", "operator.write"],
    device_key_path=".keys/device.key"  # Ed25519 keys
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

### DeviceAuth

Ed25519 device authentication:

```python
from openclaw import DeviceAuth

# Auto-generate or load existing
auth = DeviceAuth(key_path=".keys/device.key")

# Sign challenge payload
signature = auth.sign_payload(challenge_string)

# Get public key for Gateway
public_key = auth.get_public_key_raw()
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

---

## Device Authentication

Gateway requires Ed25519 device signing for secure authentication:

### Key Generation

```python
# Automatic on first run
from openclaw import DeviceAuth
auth = DeviceAuth(key_path=".keys/device.key")
```

### Manual Key Setup

```bash
# Keys are auto-generated in .keys/ directory
# .keys/device.key  - Private key (keep secret!)
# .keys/device.pub  - Public key
```

---

## Configuration

### Gateway Config (claw/config/default.json5)

```json5
{
  gateway: {
    port: 18789,
    host: "0.0.0.0"
  },
  channels: {
    telegram: {
      enabled: true,
      botToken: "YOUR_BOT_TOKEN",
      dmPolicy: "pairing"
    }
  }
}
```

### Archon AI Config (.env)

```bash
OPENCLAW_GATEWAY_URL=ws://localhost:18789
TELEGRAM_BOT_TOKEN=your_token_here
```

---

## Testing

### Basic Connection Test

```bash
python test_gateway.py
```

Expected output:
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

### Real Messages Test

```bash
python test_real_messages.py
```

### Full E2E Test

```bash
python test_end_to_end.py --interactive
```

---

## Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `OPENCLAW_GATEWAY_URL` | Gateway WebSocket URL | `ws://localhost:18789` |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot API token | `123:abc...` |
| `WHATSAPP_SESSION` | WhatsApp session | `...` |
| `OPENAI_API_KEY` | OpenAI API key | `sk-...` |
| `ANTHROPIC_API_KEY` | Anthropic API key | `sk-ant-...` |

---

## Troubleshooting

### Connection refused

```bash
# Check Gateway is running
curl http://localhost:18789/health

# Check port
netstat -an | grep 18789
```

### Protocol mismatch

- Gateway must send `connect.challenge` before handshake
- Both sides must support Protocol v3
- Check Gateway version

### Authentication failed

- Verify Ed25519 keys exist in `.keys/`
- Check device_key_path in config
- Ensure Gateway allows device auth

### Messages not received

- Check channel is configured (Telegram bot token)
- Ensure user is paired (see Telegram Bot guide)
- Check Gateway logs: `pnpm gateway:dev --verbose`

---

## Docker Full Stack

```bash
# Create .env
cat > .env << EOF
TELEGRAM_BOT_TOKEN=your_token
OPENAI_API_KEY=your_key
ANTHROPIC_API_KEY=your_key
EOF

# Start stack
make fullstack-up

# Check status
curl http://localhost:8000/health
```

---

## Related Documentation

- [Quick Start](../getting-started/quick-start.md)
- [Telegram Bot](../getting-started/telegram-bot.md)
- [Commands Reference](../reference/commands.md)
