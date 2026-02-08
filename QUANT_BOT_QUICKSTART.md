# 🚀 @quant_dev_ai_bot Quick Start

Быстрый запуск Archon AI с Telegram ботом @quant_dev_ai_bot.

## ⚡ Быстрый старт (3 шага)

### Шаг 1: Запустите OpenClaw Gateway

```powershell
cd claw
pnpm gateway:dev
```

### Шаг 2: Настройте бота (в новом терминале)

```powershell
cd archon_ai
python setup_quant_bot.py
```

Или вручную:
```powershell
# Создайте конфиг
copy openclaw_config.json5 claw\config\default.json5

# Запустите Gateway
cd claw && pnpm gateway:dev
```

### Шаг 3: Запустите Archon AI

```powershell
python run_quant_bot.py
```

## 💬 Использование

1. Откройте Telegram и найдите: **@quant_dev_ai_bot**
2. Отправьте `/start`
3. Вы получите **pairing code** (код подтверждения)
4. В терминале Gateway выполните:
   ```powershell
   cd claw
   pnpm openclaw pairing approve telegram <КОД_ИЗ_ТЕЛЕГРАМ>
   ```
5. Отправляйте сообщения боту — они будут отображаться в `run_quant_bot.py`

## 🧪 Тестирование

### Проверка подключения
```powershell
python test_gateway.py
```

### Интерактивный тест
```powershell
python test_end_to_end.py --interactive
```

### Полный E2E с реальными сообщениями
```powershell
python test_real_messages.py
```

## 📊 Что происходит при получении сообщения

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

## 🔧 Команды

| Команда | Описание |
|---------|----------|
| `make gateway-dev` | Запуск Gateway |
| `make gateway-test` | Тест подключения |
| `python run_quant_bot.py` | Archon AI + бот |
| `python setup_quant_bot.py` | Полная настройка |

## ⚙️ Конфигурация

Бот настроен в `claw/config/default.json5`:

```json5
{
  channels: {
    telegram: {
      enabled: true,
      botToken: "YOUR_TELEGRAM_BOT_TOKEN",  // Получите от @BotFather
      dmPolicy: "pairing",  // безопасность: только одобренные пользователи
    },
  },
}
```

## 🔒 Безопасность

- **Pairing policy**: Новые пользователи должны быть одобрены
- **RBAC**: Проверка прав доступа
- **Circuit Breaker**: Автономность с 4 уровнями
- **Kernel validation**: Проверка намерений

## 🐛 Troubleshooting

### "Connection refused"
```powershell
# Проверьте, что Gateway запущен
curl http://localhost:18789/health

# Или
netstat -an | findstr 18789
```

### "Pairing required"
1. Отправьте сообщение боту в Telegram
2. Получите код (например: `ABC123`)
3. Выполните: `pnpm openclaw pairing approve telegram ABC123`

### "Bot not responding"
- Убедитесь, что токен правильный
- Проверьте логи Gateway: добавьте `--verbose`

## 📁 Файлы

| Файл | Назначение |
|------|------------|
| `setup_quant_bot.py` | Автоматическая настройка |
| `run_quant_bot.py` | Основной скрипт для запуска |
| `test_gateway.py` | Тест подключения |
| `openclaw_config.json5` | Конфиг бота |
| `claw/` | OpenClaw Gateway (форк) |

## 🎯 Следующие шаги

1. **Добавьте свою логику** в `run_quant_bot.py` → метод `_handle_incoming_message`
2. **Настройте Circuit Breaker** для production
3. **Подключите Debate Pipeline** для сложных запросов
4. **Добавьте другие каналы**: WhatsApp, Slack

## 📞 Поддержка

Вопросы по OpenClaw: https://docs.openclaw.ai
Вопросы по Archon AI: см. `AGENTS.md`
