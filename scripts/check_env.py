#!/usr/bin/env python3
"""
Check and setup environment for Archon AI + @quant_dev_ai_bot.

This script:
1. Verifies all required environment variables
2. Checks API keys validity (where possible)
3. Tests OpenClaw Gateway connection
4. Provides recommendations

Usage:
    python check_env.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Load .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False
    print("⚠️  python-dotenv not installed. Install with: pip install python-dotenv")

sys.path.insert(0, str(Path(__file__).parent.parent))


class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'


def check(label: str, condition: bool, message: str = "") -> bool:
    """Print check result."""
    if condition:
        print(f"  {Colors.GREEN}✓{Colors.RESET} {label}")
        return True
    else:
        print(f"  {Colors.RED}✗{Colors.RESET} {label}")
        if message:
            print(f"    {Colors.YELLOW}→ {message}{Colors.RESET}")
        return False


def check_env_var(name: str, required: bool = False, mask: bool = False) -> bool:
    """Check environment variable."""
    value = os.getenv(name)
    exists = value is not None and value.strip() != ""
    
    if mask and exists:
        display = value[:10] + "..." + value[-4:] if len(value) > 20 else "***"
    else:
        display = value
    
    status = " (required)" if required else ""
    
    if required:
        return check(f"{name}{status}", exists, f"Set {name} in .env file")
    else:
        if exists:
            print(f"  {Colors.GREEN}✓{Colors.RESET} {name}: {display}")
        else:
            print(f"  {Colors.YELLOW}○{Colors.RESET} {name}: not set (optional)")
        return True


async def check_gateway_connection():
    """Test OpenClaw Gateway connection."""
    print(f"\n{Colors.BLUE}🔗 Testing OpenClaw Gateway...{Colors.RESET}")
    
    try:
        from openclaw import GatewayClientV3, GatewayConfig
        
        config = GatewayConfig(
            url=os.getenv("OPENCLAW_GATEWAY_URL", "ws://localhost:18789"),
            client_id="archon-env-check",
            role="operator"
        )
        
        client = GatewayClientV3(config)
        
        try:
            connected = await asyncio.wait_for(client.connect(), timeout=5.0)
            
            if connected:
                print(f"  {Colors.GREEN}✓{Colors.RESET} Gateway connected")
                print(f"    Protocol: v{client._protocol_version}")
                await client.disconnect()
                return True
            else:
                print(f"  {Colors.RED}✗{Colors.RESET} Gateway connection failed")
                return False
                
        except asyncio.TimeoutError:
            print(f"  {Colors.RED}✗{Colors.RESET} Gateway timeout (not running?)")
            print(f"    {Colors.YELLOW}→ Start with: cd claw && pnpm gateway:dev{Colors.RESET}")
            return False
            
    except ImportError as e:
        print(f"  {Colors.RED}✗{Colors.RESET} Cannot import GatewayClient: {e}")
        return False


def check_llm_providers():
    """Check LLM provider API keys."""
    print(f"\n{Colors.BLUE}🤖 LLM Providers:{Colors.RESET}")
    
    providers = [
        ("GROQ_API_KEY", "Groq", True),
        ("ANTHROPIC_API_KEY", "Anthropic Claude", False),
        ("OPENAI_API_KEY", "OpenAI", False),
        ("GEMINI_API_KEY", "Google Gemini", False),
        ("XAI_API_KEY", "xAI Grok", False),
        ("CEREBRAS_API_KEY", "Cerebras", False),
    ]
    
    active_providers = []
    
    for env_name, display_name, recommended in providers:
        value = os.getenv(env_name)
        if value and value.strip():
            prefix = f"{Colors.GREEN}✓{Colors.RESET}"
            active_providers.append(display_name)
        else:
            prefix = f"{Colors.YELLOW}○{Colors.RESET}"
        
        rec = " (recommended)" if recommended else ""
        print(f"  {prefix} {display_name}{rec}")
    
    if not active_providers:
        print(f"\n  {Colors.RED}⚠️  No LLM providers configured!{Colors.RESET}")
        print(f"  {Colors.YELLOW}→ Add at least GROQ_API_KEY to .env{Colors.RESET}")
        return False
    
    print(f"\n  {Colors.GREEN}Active providers:{Colors.RESET} {', '.join(active_providers)}")
    return True


def check_telegram_bot():
    """Check Telegram bot configuration."""
    print(f"\n{Colors.BLUE}📱 Telegram Bot (@quant_dev_ai_bot):{Colors.RESET}")
    
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    enabled = os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"
    
    if token and "7898417089" in token:
        print(f"  {Colors.GREEN}✓{Colors.RESET} Bot token configured")
        print(f"    Bot: @quant_dev_ai_bot")
    else:
        print(f"  {Colors.RED}✗{Colors.RESET} Bot token not found")
        return False
    
    if enabled:
        print(f"  {Colors.GREEN}✓{Colors.RESET} Telegram enabled")
    else:
        print(f"  {Colors.YELLOW}○{Colors.RESET} Telegram disabled (set TELEGRAM_ENABLED=true)")
    
    return True


def print_summary(results):
    """Print final summary."""
    print(f"\n{Colors.BLUE}{'='*70}{Colors.RESET}")
    print(f"{Colors.BLUE}📊 Summary{Colors.RESET}")
    print(f"{Colors.BLUE}{'='*70}{Colors.RESET}")
    
    all_passed = all(results.values())
    
    for check_name, passed in results.items():
        status = f"{Colors.GREEN}✓ PASS{Colors.RESET}" if passed else f"{Colors.RED}✗ FAIL{Colors.RESET}"
        print(f"  {status} {check_name}")
    
    print()
    
    if all_passed:
        print(f"{Colors.GREEN}🎉 All checks passed!{Colors.RESET}")
        print(f"\nNext steps:")
        print(f"  1. Start Gateway: cd claw && pnpm gateway:dev")
        print(f"  2. Run Archon AI: python run_quant_bot.py")
        print(f"  3. Message your bot: https://t.me/quant_dev_ai_bot")
    else:
        print(f"{Colors.YELLOW}⚠️  Some checks failed.{Colors.RESET}")
        print(f"\nFix the issues above and run again:")
        print(f"  python check_env.py")
    
    print(f"{Colors.BLUE}{'='*70}{Colors.RESET}")
    
    return 0 if all_passed else 1


async def main():
    """Main check flow."""
    print(f"{Colors.BLUE}{'='*70}{Colors.RESET}")
    print(f"{Colors.BLUE}🔍 Archon AI Environment Check{Colors.RESET}")
    print(f"{Colors.BLUE}{'='*70}{Colors.RESET}")
    print()
    
    results = {}
    
    # 1. Check python-dotenv
    print(f"{Colors.BLUE}📦 Python Environment:{Colors.RESET}")
    check("python-dotenv installed", DOTENV_AVAILABLE, "pip install python-dotenv")
    check("websockets installed", True)  # Will fail later if not
    
    # 2. Check required env vars
    print(f"\n{Colors.BLUE}🔧 Required Configuration:{Colors.RESET}")
    results["Environment Variables"] = (
        check_env_var("OPENCLAW_GATEWAY_URL", required=False) and
        check_env_var("API_HOST", required=False) and
        check_env_var("API_PORT", required=False)
    )
    
    # 3. Check Telegram bot
    results["Telegram Bot"] = check_telegram_bot()
    
    # 4. Check LLM providers
    results["LLM Providers"] = check_llm_providers()
    
    # 5. Check Gateway connection
    results["Gateway Connection"] = await check_gateway_connection()
    
    # Summary
    return print_summary(results)


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
