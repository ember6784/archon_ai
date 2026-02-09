"""
@quant_dev_ai_bot - Main Runner

Runs Archon AI with OpenClaw Gateway integration using SecureGatewayBridge.
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

from kernel.openclaw_integration import create_secure_bridge, IntegrationConfig
from kernel.execution_kernel import ExecutionKernel
from enterprise.event_bus import EventBus, EventType


class QuantBotRunner:
    """Runner for @quant_dev_ai_bot using SecureGatewayBridge."""

    def __init__(self):
        self.bridge = None
        self.message_count = 0

    async def handle_telegram_message(self, message):
        """Handle incoming Telegram message through secure bridge."""
        self.message_count += 1

        print(f"\n{'='*50}")
        print(f"[NEW] Telegram Message #{self.message_count}")
        print(f"{'='*50}")
        print(f"From: {message.user_name} (ID: {message.user_id})")
        print(f"Message: {message.message}")
        print(f"{'='*50}\n")

        # Generate response
        response_text = await self._generate_response(message.message)

        # Return BridgeResponse
        from enterprise.gateway_bridge import BridgeResponse
        return BridgeResponse(
            success=True,
            response=response_text,
            metadata={"message_count": self.message_count}
        )

    async def _generate_response(self, message: str) -> str:
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
[+] Kernel: Активен через SecureGatewayBridge
[+] Circuit Breaker: Включен
[+] Device Auth: Ed25519
[#] Сообщений обработано: {self.message_count}"""

        elif 'время' in message_lower or 'time' in message_lower:
            from datetime import datetime
            return f"[TIME] Текущее время: {datetime.now().strftime('%H:%M:%S')}"

        elif 'о' in message_lower and 'бот' in message_lower:
            return """[BOT] @quant_dev_ai_bot

Я - AI ассистент на базе:
• OpenClaw Gateway с Device Auth (Ed25519)
• Archon AI Execution Kernel
• Circuit Breaker безопасности
• Multi-Agent Team Debate Pipeline

Защищён SecureGatewayBridge с kernel validation."""

        else:
            # Default response
            return f"🔄 Получено: \"{message}\"\n\n(Для справки отправьте /help)"

    async def start(self):
        """Start the bot with SecureGatewayBridge."""

        print("\n" + "=" * 60)
        print("       @quant_dev_ai_bot - Archon AI Bot")
        print("         Secured by OpenClaw Gateway + Device Auth")
        print("=" * 60)

        # Create secure bridge
        self.bridge = create_secure_bridge(
            integration_config=IntegrationConfig(
                ws_url="ws://localhost:18789",
                enable_circuit_breaker=True,
                enable_kernel_validation=True,
                kernel_environment="prod"
            )
        )

        # Connect to gateway
        print("[BRIDGE] Connecting to OpenClaw Gateway...")
        connected = await self.bridge.connect_gateway_v3()

        if not connected:
            print("[ERROR] Failed to connect to Gateway")
            return

        print("[+] Connected to Gateway with Device Auth!")

        # Register secure handler for all messages
        self.bridge.register_secure_handler(
            pattern="*",  # Match all messages
            handler=self.handle_telegram_message,
            operation_name="telegram_handler"
        )

        print("[+] Secure handler registered")
        print("\n[BOT] @quant_dev_ai_bot is running!")
        print("Send a message to @quant_dev_ai_bot in Telegram")
        print("Press Ctrl+C to stop\n")

        # Keep running
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\n[STOP] Shutting down...")

    async def stop(self):
        """Stop the bot."""
        if self.bridge:
            # Note: SecureGatewayBridge doesn't have explicit disconnect method
            # But GatewayClientV3 has disconnect
            if hasattr(self.bridge, '_gateway_client') and self.bridge._gateway_client:
                await self.bridge._gateway_client.disconnect()
        print("[STOP] Bot stopped")


async def main():
    """Main entry point."""
    runner = QuantBotRunner()

    # Setup signal handlers
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(runner.stop()))
        except NotImplementedError:
            # Windows doesn't support signal handlers
            pass

    try:
        await runner.start()
    except KeyboardInterrupt:
        print("\n[STOP] Shutting down...")
        await runner.stop()


if __name__ == "__main__":
       print("""
    ================================================
       @quant_dev_ai_bot - Archon AI Bot
         Secured by OpenClaw Gateway + Device Auth
    ================================================
    """)

if __name__ == "__main__":
    asyncio.run(main())
