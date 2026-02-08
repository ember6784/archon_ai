# 📚 Command Reference - Archon AI + OpenClaw Gateway

Быстрый справочник по всем командам для работы с системой.

---

## 🚀 Быстрый старт (3 команды)

```powershell
# 1. Проверка окружения
python check_env.py

# 2. Запуск Gateway (Terminal 1)
cd claw && node scripts/run-node.mjs gateway --allow-unconfigured --verbose

# 3. Запуск бота (Terminal 2)
python run_quant_bot.py
```

---

## 🌉 OpenClaw Gateway

### Запуск Gateway

```powershell
# Базовый запуск (с конфигом)
cd claw
node scripts/run-node.mjs gateway --verbose

# Без авторизации (для разработки)
node scripts/run-node.mjs gateway --allow-unconfigured --verbose

# С указанием порта
node scripts/run-node.mjs gateway --port 18789 --verbose

# Только WebSocket (без каналов)
$env:OPENCLAW_SKIP_CHANNELS="1"
node scripts/run-node.mjs gateway --verbose
```

### Остановка Gateway

```powershell
# Корректная остановка
node openclaw.mjs gateway stop

# Принудительная остановка
node openclaw.mjs gateway stop --force

# Или через taskkill
taskkill /PID <PID> /F
```

### Настройка Gateway

```powershell
# Интерактивная настройка
node openclaw.mjs onboard

# Просмотр конфигурации
node openclaw.mjs config

# Изменение настройки
node openclaw.mjs configure <key>=<value>

# Примеры:
node openclaw.mjs configure gateway.port=18789
node openclaw.mjs configure channels.telegram.enabled=true
```

### Проверка состояния

```powershell
# Проверка здоровья
curl http://localhost:18789/health

# Doctor - диагностика
node openclaw.mjs doctor

# Статус Gateway
node openclaw.mjs status
```

---

## 🤖 Archon AI

### Make команды

```powershell
# Основные
make install          # Установка зависимостей
make run              # Запуск API сервера
make test             # Запуск тестов
make lint             # Проверка кода
make format           # Форматирование кода

# Gateway
make gateway-dev      # Запуск Gateway (через pnpm)
make gateway-test     # Тест подключения
make gateway-e2e      # E2E тест

# Бот (@quant_dev_ai_bot)
make quant-setup      # Настройка бота
make quant-run        # Запуск с ботом
make quant-test       # Тест бота

# Окружение
make check-env        # Проверка .env
make setup-env        # Настройка из .env
make run-bot          # Запуск бота

# Docker
make docker-build     # Сборка образов
make docker-up        # Запуск сервисов
make docker-down      # Остановка
make docker-dev       # Dev окружение
make fullstack-up     # Полный стек + Gateway
make fullstack-down   # Остановка стека
```

### Python скрипты

```powershell
# Проверка окружения
python check_env.py

# Настройка из .env
python setup_from_env.py

# Базовый тест Gateway
python test_gateway.py

# Тест с реальными сообщениями
python test_real_messages.py

# Полный E2E тест
python test_end_to_end.py --interactive

# Запуск бота
python run_quant_bot.py

# Запуск бота (альтернативы)
.\run_bot.bat
.\run_bot.ps1
```

### API Endpoints

```powershell
# Health check
curl http://localhost:8000/health

# Circuit Breaker статус
curl http://localhost:8000/api/v1/circuit_breaker/status

# Запись активности человека
curl -X POST http://localhost:8000/api/v1/circuit_breaker/record_activity \
  -H "Content-Type: application/json" \
  -d '{"action": "manual_review"}'

# Дебат (code review)
curl -X POST http://localhost:8000/api/v1/debate/start \
  -H "Content-Type: application/json" \
  -d '{
    "code": "def add(a, b): return a + b",
    "requirements": "Create add function",
    "file_path": "math.py"
  }'
```

---

## 💬 Telegram Bot (@quant_dev_ai_bot)

### Pairing (подключение пользователей)

```powershell
# Получить код в Telegram → отправить /start боту

# Одобрить pairing (в терминале Gateway)
cd claw
node openclaw.mjs pairing approve telegram <CODE>

# Просмотр списка ожидающих
node openclaw.mjs pairing list

# Отклонить
node openclaw.mjs pairing reject telegram <CODE>
```

### Отправка сообщений

```powershell
# Отправить сообщение пользователю
node openclaw.mjs message send --to <USER_ID> --message "Hello"

# Отправить через API
node openclaw.mjs agent --message "Your message" --to <USER_ID>
```

---

## 🛠️ Устранение неполадок

### Gateway не запускается

```powershell
# Проверить занятость порта
netstat -ano | findstr 18789

# Освободить порт
taskkill /PID <PID> /F

# Или используйте другой порт
node scripts/run-node.mjs gateway --port 18888
```

### Проблемы с подключением

```powershell
# Проверка WebSocket
curl -i -N -H "Connection: Upgrade" \
  -H "Upgrade: websocket" \
  -H "Host: localhost:18789" \
  -H "Origin: http://localhost" \
  http://localhost:18789

# Логи Gateway
cd claw
node openclaw.mjs logs

# Debug режим
node scripts/run-node.mjs gateway --verbose --debug
```

### Сброс конфигурации

```powershell
# Сброс Gateway
node openclaw.mjs gateway --reset

# Полный сброс
node openclaw.mjs reset

# Удаление lock-файла
rm ~/.openclaw/gateway.lock
```

---

## 📦 Управление Skills

```powershell
# Список доступных
node openclaw.mjs skills list

# Установить skill
node openclaw.mjs skills install github
node openclaw.mjs skills install openai-image-gen
node openclaw.mjs skills install openai-whisper

# Установить все
node openclaw.mjs skills install --all

# Обновить
node openclaw.mjs skills update

# Удалить
node openclaw.mjs skills remove <skill-name>
```

---

## 🐳 Docker

```powershell
# Сборка
docker-compose build

# Запуск
docker-compose up -d

# Логи
docker-compose logs -f archon-api
docker-compose logs -f openclaw-gateway

# Полный стек (Archon + Gateway)
docker-compose -f docker-compose.fullstack.yml up -d

# Остановка
docker-compose down
docker-compose -f docker-compose.fullstack.yml down
```

---

## 🔍 Отладка

```powershell
# Проверка импортов Python
python check_imports.py

# Проверка переменных окружения
python check_env.py

# Тест Gateway
python test_gateway.py

# Проверка API
curl http://localhost:8000/health | python -m json.tool
```

---

## 📝 Полезные алиасы (добавьте в PowerShell $PROFILE)

```powershell
# Archon AI
function archon-start { cd E:\archon_ai; python run_quant_bot.py }
function archon-check { cd E:\archon_ai; python check_env.py }
function archon-api { cd E:\archon_ai; make run }

# Gateway
function gateway-start { cd E:\archon_ai\claw; node scripts/run-node.mjs gateway --verbose }
function gateway-stop { cd E:\archon_ai\claw; node openclaw.mjs gateway stop }
function gateway-logs { cd E:\archon_ai\claw; node openclaw.mjs logs }

# Docker
function docker-fullstack { cd E:\archon_ai; make fullstack-up }
```

---

## 🔗 Полезные ссылки

- **Gateway Dashboard**: http://localhost:18789/overview
- **API Docs**: http://localhost:8000/docs
- **Telegram Bot**: https://t.me/quant_dev_ai_bot

---

## ⚡ Emergency Commands

```powershell
# Полный перезапуск системы

# 1. Остановить всё
node openclaw.mjs gateway stop
taskkill /F /IM python.exe
taskkill /F /IM node.exe

# 2. Очистка
make clean

# 3. Перезапуск
# Terminal 1
cd claw && node scripts/run-node.mjs gateway --allow-unconfigured --verbose

# Terminal 2
cd archon_ai && python run_quant_bot.py
```
