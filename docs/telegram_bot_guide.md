# Telegram Bot @quant_dev_ai_bot - Руководство

## Текущий статус

**Бот работает!** Отправьте `/start` в Telegram.

| Параметр | Значение |
|----------|----------|
| Бот | @quant_dev_ai_bot |
| User ID | 554557965 |
| Pairing Code | 54M9QKBD (использован) |
| Статус | ✅ Paired & Working |

## Как пользоваться

### Отправка сообщений

1. Откройте Telegram
2. Найдите бота: @quant_dev_ai_bot
3. Отправьте команду:
   - `/start` - Приветствие
   - `/help` - Справка
   - Любое сообщение - обработка через Pi Agent

### Что происходит за кулисами

```
Telegram → OpenClaw Gateway → Pi Agent (xai/grok-code-fast-1)
                                  ↓
                            Ответ пользователю
```

**Важно:** Archon AI Kernel НЕ используется сейчас!
Бот отвечает через встроенный Pi Agent OpenClaw.

## Подключение Archon AI

Чтобы сообщения проходили через Archon AI Kernel:

### Вариант A: Получить device token от OpenClaw

```bash
# 1. Открыть OpenClaw Web UI
# http://localhost:3000

# 2. Создать device fingerprint
# Settings → Devices → Add Device

# 3. Скопировать token
```

### Вариант B: Реализовать Ed25519 device signing

```python
# В openclaw/gateway_v3.py:
from cryptography.hazmat.primitives.asymmetric import ed25519

# Generate keys
private_key = ed25519.Ed25519PrivateKey.generate()
public_key = private_key.public_key()

# Sign payload
signature = private_key.sign(payload_to_sign)
```

## Структура проекта

```
archon_ai/
├── openclaw/
│   ├── __init__.py
│   ├── gateway_v3.py          # Python клиент (требует fixes)
│   ├── gateway.py
│   └── channels.py
│
├── kernel/
│   ├── execution_kernel.py    # ✅ Готов
│   ├── openclaw_integration.py # ✅ Готов
│   ├── dynamic_circuit_breaker.py # ✅ Готов
│   └── invariants.py          # ✅ Готов
│
├── test_gateway.py            # ✅ Создан
├── test_end_to_end.py         # ✅ Создан
├── test_real_messages.py      # ✅ Создан
├── run_quant_bot.py           # ✅ Создан
└── setup_quant_bot.py         # ✅ Создан
```

## Следующие шаги

### P0: Подключить Archon AI к Gateway

1. **Реализовать device signing** ИЛИ получить валидный token
2. **Подключить SecureGatewayBridge** к Gateway
3. **Перехватывать события** message от Gateway
4. **Проверять** через ExecutionKernel

### P1: Настроить обработчики

```python
# В run_quant_bot.py:
bridge = SecureGatewayBridge()
bridge.register_secure_handler(
    pattern="*",
    handler=handle_message,
    operation_name="telegram_handler"
)
```

## Полезные команды

```bash
# Проверить Gateway
netstat -an | findstr 18789

# Запустить Archon AI
cd E:\archon_ai
python -m enterprise.main

# Тест соединения
python test_gateway.py

# Слушать сообщения
python test_real_messages.py
```

## Troubleshooting

### Бот не отвечает
- Проверьте Gateway: `netstat -an | findstr 18789`
- Проверьте pairing: `cd claw && pnpm openclaw pairing list`

### Archon AI не подключается
- Ошибка: `policy violation` → требуется device signing
- Решение: Вариант A или B выше

## Ссылки

- [OpenClaw Gateway docs](../claw/docs/)
- [TELEGRAM_INTEGRATION_STATUS.md](../TELEGRAM_INTEGRATION_STATUS.md)
- [NEXT_SESSION.md](../NEXT_SESSION.md)
