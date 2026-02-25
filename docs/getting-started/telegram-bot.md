# Telegram Bot Setup

Настройка и использование Telegram бота с Archon AI.

---

## Current Status

| Parameter | Value |
|-----------|-------|
| Bot | @your_telegram_bot |
| Gateway Port | 18789 |
| Protocol | v3 (Ed25519 device auth) |

---

## Quick Start (3 Steps)

### Step 1: Start OpenClaw Gateway

```bash
cd claw
pnpm gateway:dev
```

### Step 2: Configure Bot

```bash
# Automatic setup
python setup_quant_bot.py

# Or manually: copy config
cp openclaw_config.json5 claw/config/default.json5
```

### Step 3: Run Archon AI

```bash
python run_quant_bot.py
# Or: make run-bot
```

---

## Pairing Process

### 1. Start in Telegram

1. Open Telegram and find your bot: **@your_telegram_bot**
2. Send `/start`
3. You'll receive a **pairing code** (e.g., `ABC123`)

### 2. Approve Pairing

```bash
cd claw
pnpm openclaw pairing approve telegram ABC123
```

### 3. Ready!

Send messages to the bot — they'll be processed through Archon AI.

---

## Configuration

### Bot Config (claw/config/default.json5)

```json5
{
  channels: {
    telegram: {
      enabled: true,
      botToken: "YOUR_TELEGRAM_BOT_TOKEN",  // Get from @BotFather
      dmPolicy: "pairing",  // Security: only approved users
    },
  },
}
```

### Getting Bot Token

1. Open Telegram and find **@BotFather**
2. Send `/newbot`
3. Follow instructions
4. Copy the token to your config

---

## Message Flow

```
[Telegram] → [Gateway] → [Archon AI]
                 ↓
          [Protocol v3 Handshake]
                 ↓
       [SecureGatewayBridge]
                 ↓
    ┌────────────┼────────────┐
    ↓            ↓            ↓
[RBAC]     [Circuit]    [Kernel]
Check      [Breaker]    Validation
                ↓
         [MAT/Debate]
         (if needed)
                ↓
         [Response]
```

---

## Security Features

| Feature | Description |
|---------|-------------|
| **Pairing policy** | New users must be approved |
| **RBAC** | Role-based access control |
| **Circuit Breaker** | 4-level autonomy system |
| **Kernel validation** | Intent contracts + invariants |
| **Ed25519 signing** | Device authentication |

---

## Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Initialize and get pairing code |
| `/help` | Show help message |
| Any message | Processed through Archon AI |

---

## Testing

### Connection Test

```bash
python test_gateway.py
```

### Interactive Test

```bash
python test_end_to_end.py --interactive
```

### Real Messages Test

```bash
python test_real_messages.py
```

---

## Device Authentication

The bot uses Ed25519 device signing for secure Gateway authentication:

```python
from openclaw import GatewayClientV3, DeviceAuth

# Device auth is handled automatically
config = GatewayConfig(
    url="ws://localhost:18789",
    client_id="archon-ai-telegram",
    role="operator",
    device_key_path=".keys/device.key"  # Auto-generated
)

client = GatewayClientV3(config)
await client.connect()
```

### Key Files

| File | Purpose |
|------|---------|
| `.keys/device.key` | Ed25519 private key |
| `.keys/device.pub` | Public key (for Gateway) |

---

## Troubleshooting

### "Connection refused"

```bash
# Check Gateway
curl http://localhost:18789/health

# Check port
netstat -an | grep 18789
```

### "Pairing required"

1. Send `/start` to bot in Telegram
2. Get code (e.g., `ABC123`)
3. Approve: `pnpm openclaw pairing approve telegram ABC123`

### "Bot not responding"

- Verify bot token is correct
- Check Gateway logs: `pnpm gateway:dev --verbose`
- Ensure pairing was approved

### "Policy violation"

This indicates device auth is required. The `run_quant_bot.py` handles this automatically with DeviceAuth.

---

## Advanced: Custom Handlers

Add your own message processing logic:

```python
# In run_quant_bot.py or custom script
from kernel import create_secure_bridge

async def handle_telegram_message(event):
    """Custom message handler."""
    message = event.payload
    
    # Your logic here
    response = f"Echo: {message.get('text', '')}"
    
    return {"response": response}

# Register handler
bridge = create_secure_bridge(config)
bridge.register_secure_handler(
    pattern="*",
    handler=handle_telegram_message,
    operation_name="telegram_handler"
)
```

---

## Related Files

| File | Purpose |
|------|---------|
| `run_quant_bot.py` | Main bot script |
| `setup_quant_bot.py` | Automatic setup |
| `test_gateway.py` | Connection test |
| `openclaw_config.json5` | Bot configuration |
| `openclaw/gateway_v3.py` | Gateway client |
| `enterprise/openclaw_integration.py` | Secure bridge |

---

## Next Steps

1. **Add custom logic** in your message handler
2. **Configure Circuit Breaker** for production
3. **Add Debate Pipeline** for complex queries
4. **Connect other channels**: WhatsApp, Slack
