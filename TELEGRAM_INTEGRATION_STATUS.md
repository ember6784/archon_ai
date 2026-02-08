# Статус интеграции OpenClaw + Archon AI
**Дата обновления:** 2026-02-08

## Текущий статус

### Что работает ✅

| Компонент | Статус | Детали |
|-----------|--------|--------|
| OpenClaw Gateway | ✅ Запущен | PID 1308, порт 18789 |
| Telegram бот @quant_dev_ai_bot | ✅ Работает | Пользователь 554557965 paired |
| OpenClaw Pi Agent | ✅ Отвечает | xai/grok-code-fast-1 |
| Archon AI Kernel | ✅ Готов | ExecutionKernel + Circuit Breaker |
| Тестовые файлы | ✅ Созданы | 5 тестовых скриптов |

### Что не работает ❌

| Компонент | Проблема | Решение |
|-----------|----------|---------|
| Python GatewayClientV3 | ❌ Handshake fails | Требуется Ed25519 device signing |
| Прямая интеграция | ❌ Middleware не подключён | Требует валидный auth token |

## Архитектура на данный момент

```
┌─────────────────────────────────────────────────────────────────┐
│                    Telegram (@quant_dev_ai_bot)                │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    OpenClaw Gateway (18789)                     │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Built-in Pi Agent (xai/grok-code-fast-1)               │   │
│  │  - Обрабатывает все сообщения                            │   │
│  │  - Не использует Archon AI Kernel                        │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼ (НЕ ПОДКЛЮЧЕНО)
┌─────────────────────────────────────────────────────────────────┐
│                    Archon AI (Python)                          │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  ExecutionKernel + Circuit Breaker                      │   │
│  │  SecureGatewayBridge (не подключён к Gateway)           │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Проблема handshake

OpenClaw Gateway требует **одного из двух** для подключения:

1. **Валидный auth token** — выданный Gateway
2. **Device signing** — Ed25519 подпись устройства

Python клиент `GatewayClientV3` сейчас не поддерживает ни один из вариантов.

### Текущая ошибка
```
< CLOSE 1008 (policy violation) invalid connect params: ... match a schema in anyOf
```

Это означает, что Gateway отклоняет connect request потому что:
- auth.token не валидный (test_token_123 не принимается)
- device.auth требует publicKey + signature (Ed25519)

## Варианты интеграции

### Вариант 1: Использовать существующую архитектуру
```
Telegram → OpenClaw Gateway → Pi Agent (ответы)
                    ↓
         (отдельный процесс) Archon AI
                    ↓
         только для_sensitive операций
```

**Плюсы:**
- Telegram бот уже работает
- Минимум изменений
- OpenClaw UI доступен

**Минусы:**
- Archon AI Kernel не валидирует сообщения
- Нет единой точки контроля

### Вариант 2: Реализовать device signing (сложно)
```python
# Требуется в openclaw/gateway_v3.py:
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

# Generate keypair
private_key = ed25519.Ed25519PrivateKey.generate()
public_key = private_key.public_key()

# Sign challenge payload
signature = private_key.sign(payload)
```

**Сложность:** Высокая, требует криптографии

### Вариант 3: Получить валидный device token от OpenClaw

1. Открыть OpenClaw Web UI (http://localhost:3000)
2. Создать device fingerprint
3. Получить device token
4. Использовать в Python клиенте

## Следующие шаги

### Приоритет P0: Запустить бота с Archon AI

1. **Создать middleware** — перехватывать события от Gateway
2. **Реализовать device signing** или получить валидный token
3. **Подключить SecureGatewayBridge** к Gateway
4. **Настроить обработчики** для Telegram сообщений

### Приоритет P1: Тестирование

1. Отправить сообщение в Telegram
2. Убедиться, что оно проходит через Archon Kernel
3. Проверить валидацию Intent Contracts
4. Протестировать Circuit Breaker

## Файлы для работы

| Файл | Описание |
|------|----------|
| `openclaw/gateway_v3.py` | Python клиент (требует fixes) |
| `kernel/openclaw_integration.py` | Интеграция с Archon |
| `test_real_messages.py` | Тест приёма сообщений |
| `run_quant_bot.py` | Запуск бота |

## Команды для тестирования

```powershell
# 1. Проверить Gateway
netstat -an | findstr 18789

# 2. Тест соединения (сейчас fails)
cd E:\archon_ai
python test_gateway.py

# 3. Запустить Archon AI
python -m enterprise.main

# 4. Отправить сообщение боту
# В Telegram: @quant_dev_ai_bot
# Сообщение: /start
```

## Полезные ссылки

- OpenClaw docs: `claw/docs/`
- Gateway CLI: `cd claw && pnpm openclaw --help`
- Device auth: `claw/src/gateway/device-auth.ts`
- **План следующей сессии:** [NEXT_SESSION.md](NEXT_SESSION.md#session-9-goals-2026-02-08---openclaw-device-signing)

---

## План следующей сессии (Session 9)

**Цель:** Подключить Archon AI к OpenClaw Gateway через Ed25519 device signing

### Задачи:

1. **Реализовать DeviceAuth class** в `openclaw/gateway_v3.py`
   - Генерация Ed25519 ключей
   - Метод `sign_payload()` для подписи challenge
   - Метод `get_public_key_raw()` для получения publicKey

2. **Обновить connect request** с device auth:
   ```python
   device = {
       "id": device_id,
       "publicKey": public_key,
       "signature": signed_payload,
       "signedAt": ts,
       "nonce": nonce
   }
   ```

3. **Тестирование handshake** — убедиться что подключение проходит

4. **Подключить SecureGatewayBridge** для перехвата сообщений

Подробнее в [NEXT_SESSION.md](NEXT_SESSION.md#session-9)
