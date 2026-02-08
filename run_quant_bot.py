"""
@quant_dev_ai_bot - Main Runner

Runs Archon AI with Telegram bot integration.
"""

import asyncio
import sys
import os
import signal
from pathlib import Path

# Add paths
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "kernel"))
sys.path.insert(0, str(Path(__file__).parent / "enterprise"))

from enterprise.main import ArchonAIApp
from kernel.execution_kernel import ExecutionKernel
from enterprise.event_bus import EventBus, EventType


class QuantBotApp(ArchonAIApp):
    """Extended Archon AI with Telegram bot handlers."""
    
    def __init__(self):
        super().__init__()
        self.message_count = 0
        
    async def _setup_telegram_handlers(self):
        """Setup Telegram message handlers."""
        
        # Subscribe to message events
        self.event_bus.subscribe(
            EventType.MESSAGE_RECEIVED,
            self._handle_telegram_message
        )
        
        print("[Telegram] Handlers registered")
    
    async def _handle_telegram_message(self, event):
        """Handle incoming Telegram message."""
        self.message_count += 1
        
        data = event.data if hasattr(event, 'data') else event
        message = data.get('message', '')
        user_id = data.get('user_id', 'unknown')
        user_name = data.get('user_name', 'User')
        
        print(f"\n{'='*50}")
        print(f"[NEW] Telegram Message #{self.message_count}")
        print(f"{'='*50}")
        print(f"From: {user_name} (ID: {user_id})")
        print(f"Message: {message}")
        print(f"{'='*50}\n")
        
        # Process through kernel
        from kernel.execution_kernel import ExecutionContext
        
        context = ExecutionContext(
            agent_id=user_id,
            operation="telegram_message",
            parameters={
                "message": message,
                "user_name": user_name,
                "channel": "telegram"
            }
        )
        
        # Validate through kernel
        kernel = ExecutionKernel()
        result = await kernel.validate_pre(context)
        
        if result.approved:
            print(f"[+] Kernel approved: {result.reason}")

            # Generate response
            response = await self._generate_response(message, context)
            print(f"[RESP] {response}")

        else:
            print(f"[-] Kernel rejected: {result.reason}")
    
    async def _generate_response(self, message: str, context) -> str:
        """Generate response to user message."""
        
        # Simple responses for demo
        message_lower = message.lower()
        
        if '/start' in message_lower or 'привет' in message_lower or 'hello' in message_lower:
            return "[HI] Привет! Я @quant_dev_ai_bot - Archon AI ассистент. Чем могу помочь?"

        elif 'помощь' in message_lower or 'help' in message_lower:
            return """[HELP] Доступные команды:
/start - Начать
/status - Статус системы
/time - Текущее время
/about - О боте"""

        elif 'статус' in message_lower or 'status' in message_lower:
            return f"""[STAT] Статус Archon AI:
[+] Gateway: Подключен
[+] Kernel: Активен
[+] Circuit Breaker: Включен
[#] Сообщений обработано: {self.message_count}"""

        elif 'время' in message_lower or 'time' in message_lower:
            from datetime import datetime
            return f"[TIME] Текущее время: {datetime.now().strftime('%H:%M:%S')}"

        elif 'о' in message_lower and 'бот' in message_lower:
            return """[BOT] @quant_dev_ai_bot

Я - AI ассистент на базе:
• OpenClaw Gateway
• Archon AI Execution Kernel
• Circuit Breaker безопасности
• Multi-Agent Team Debate Pipeline

Создан для демонстрации интеграции Archon AI + OpenClaw."""
        
        else:
            # Default response
            return f"🔄 Получено: \"{message}\"\n\n(Для справки отправьте /help)"
    
    async def start(self):
        """Start the bot."""
        await super().start()
        await self._setup_telegram_handlers()
        
        print("\n" + "=" * 50)
        print("[BOT] @quant_dev_ai_bot is running!")
        print("=" * 50)
        print("Send a message to @quant_dev_ai_bot in Telegram")
        print("Press Ctrl+C to stop\n")


async def main():
    """Main entry point."""
    app = QuantBotApp()
    
    # Setup signal handlers
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(app.stop()))
    
    try:
        await app.run()
    except KeyboardInterrupt:
        print("\n[STOP] Shutting down...")
        await app.stop()


if __name__ == "__main__":
       print("""
    ================================================
       @quant_dev_ai_bot - Archon AI Bot
           Powered by OpenClaw Gateway
    ================================================
    """)
    
    asyncio.run(main())
