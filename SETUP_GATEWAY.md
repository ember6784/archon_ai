# Setup OpenClaw Gateway Integration

## Quick Start

### 1. Start OpenClaw Gateway

```powershell
cd E:\archon_ai\claw
pnpm gateway:dev
```

Gateway будет доступен по адресу: `ws://localhost:18789`

### 2. Test Connection

```powershell
cd E:\archon_ai
python test_gateway.py
```

### 3. Run Archon AI API

```powershell
make run
# или
uvicorn enterprise.api.main:app --reload --host 0.0.0.0 --port 8000
```

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

## Protocol v3 Handshake

```
Gateway          Client
   │                │
   │◄───────────────┤  connect.challenge (nonce, ts)
   │                │
   ├───────────────►│  connect (role, scopes, device)
   │                │
   │◄───────────────┤  hello-ok (protocol, deviceToken)
   │                │
   │◄══════════════►│  tick (heartbeat every 15s)
```

## Troubleshooting

### Connection refused
- Проверьте, что Gateway запущен: `pnpm gateway:dev` в папке `claw/`
- Проверьте порт: `netstat -an | findstr 18789`

### Protocol mismatch
- Обе стороны должны поддерживать protocol v3
- Gateway должен отправить `connect.challenge` перед handshake

### Authentication failed
- Убедитесь, что `role="operator"` и scopes правильные
- Проверьте device fingerprint (для production)
