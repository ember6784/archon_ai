#!/usr/bin/env python3
"""
Setup Archon AI environment from .env file.

This script:
1. Loads configuration from .env
2. Creates OpenClaw Gateway config
3. Verifies all connections
4. Starts the integration

Usage:
    python setup_from_env.py
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("❌ python-dotenv not installed")
    print("   pip install python-dotenv")
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).parent))


def setup_gateway_config():
    """Create OpenClaw Gateway config from .env."""
    print("🔧 Creating OpenClaw Gateway config...")
    
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("❌ TELEGRAM_BOT_TOKEN not found in .env")
        return False
    
    config = {
        "channels": {
            "telegram": {
                "enabled": True,
                "botToken": token,
                "dmPolicy": "pairing",
                "groups": {
                    "*": {
                        "requireMention": True
                    }
                }
            }
        },
        "gateway": {
            "port": 18789,
            "verbose": True,
            "bind": "0.0.0.0"
        },
        "agents": {
            "defaults": {
                "model": os.getenv("DEFAULT_LLM_PROVIDER", "groq"),
                "streaming": True
            }
        },
        "logging": {
            "level": os.getenv("LOG_LEVEL", "info").lower()
        }
    }
    
    # Save config
    config_dir = Path("claw/config")
    config_dir.mkdir(parents=True, exist_ok=True)
    
    config_file = config_dir / "default.json5"
    
    # Convert to json5-like format (with comments)
    config_content = f'''// Auto-generated from .env
// Archon AI + @quant_dev_ai_bot configuration

{{
  // Telegram Bot (@quant_dev_ai_bot)
  channels: {{
    telegram: {{
      enabled: true,
      botToken: "{token}",
      dmPolicy: "pairing",
      groups: {{ "*": {{ requireMention: true }} }},
    }},
  }},
  
  // Gateway settings
  gateway: {{
    port: {os.getenv("API_PORT", "18789")},
    verbose: true,
    bind: "0.0.0.0",
  }},
  
  // Agent defaults
  agents: {{
    defaults: {{
      model: "{os.getenv("DEFAULT_LLM_PROVIDER", "groq")}",
      streaming: true,
    }},
  }},
  
  // Logging
  logging: {{
    level: "{os.getenv("LOG_LEVEL", "info").lower()}",
  }},
}}
'''
    
    config_file.write_text(config_content, encoding='utf-8')
    print(f"  ✅ Config saved: {config_file}")
    
    return True


def print_config_summary():
    """Print configuration summary."""
    print("\n" + "="*70)
    print("📋 Configuration Summary")
    print("="*70)
    
    print(f"\n🤖 Bot: @quant_dev_ai_bot")
    print(f"   Token: {'*' * 20}...{os.getenv('TELEGRAM_BOT_TOKEN', '')[-6:]}")
    
    print(f"\n🌐 Gateway:")
    print(f"   URL: {os.getenv('OPENCLAW_GATEWAY_URL', 'ws://localhost:18789')}")
    print(f"   Port: {os.getenv('API_PORT', '18789')}")
    
    print(f"\n🤖 LLM Provider: {os.getenv('DEFAULT_LLM_PROVIDER', 'groq')}")
    
    # Check which providers are configured
    providers = []
    for env_var, name in [
        ("GROQ_API_KEY", "Groq"),
        ("ANTHROPIC_API_KEY", "Anthropic"),
        ("OPENAI_API_KEY", "OpenAI"),
        ("GEMINI_API_KEY", "Gemini"),
    ]:
        if os.getenv(env_var):
            providers.append(name)
    
    if providers:
        print(f"   Available: {', '.join(providers)}")
    
    print(f"\n🔒 Security:")
    print(f"   Sandbox: {os.getenv('ENABLE_SANDBOX', 'false')}")
    print(f"   Circuit Breaker: {os.getenv('CIRCUIT_BREAKER_ENABLED', 'true')}")
    
    print("\n" + "="*70)


def create_run_scripts():
    """Create convenient run scripts."""
    print("\n📝 Creating run scripts...")
    
    # Windows batch file
    bat_content = '''@echo off
echo Starting Archon AI with @quant_dev_ai_bot...
echo.
python run_quant_bot.py
pause
'''
    
    # PowerShell script
    ps_content = '''# Archon AI + @quant_dev_ai_bot Starter
Write-Host "Starting Archon AI with @quant_dev_ai_bot..." -ForegroundColor Green
python run_quant_bot.py
'''
    
    Path("run_bot.bat").write_text(bat_content)
    Path("run_bot.ps1").write_text(ps_content)
    
    print("  ✅ run_bot.bat (Windows)")
    print("  ✅ run_bot.ps1 (PowerShell)")


async def test_connections():
    """Test all connections."""
    print("\n🔗 Testing connections...")
    
    # Test Gateway
    try:
        from openclaw import GatewayClientV3, GatewayConfig
        
        config = GatewayConfig(
            url=os.getenv("OPENCLAW_GATEWAY_URL", "ws://localhost:18789"),
            client_id="archon-setup",
            role="operator"
        )
        
        client = GatewayClientV3(config)
        
        connected = await asyncio.wait_for(client.connect(), timeout=5.0)
        
        if connected:
            print("  ✅ Gateway: Connected")
            await client.disconnect()
        else:
            print("  ⚠️  Gateway: Not running (start with: cd claw && pnpm gateway:dev)")
            
    except Exception as e:
        print(f"  ⚠️  Gateway: {e}")


def print_next_steps():
    """Print next steps."""
    print("\n" + "="*70)
    print("🚀 Next Steps")
    print("="*70)
    print()
    print("1. Start OpenClaw Gateway:")
    print("   cd claw && pnpm gateway:dev")
    print()
    print("2. In another terminal, run Archon AI:")
    print("   python run_quant_bot.py")
    print("   # or: ./run_bot.bat")
    print("   # or: ./run_bot.ps1")
    print()
    print("3. Open Telegram and message @quant_dev_ai_bot")
    print()
    print("4. If first contact, approve pairing:")
    print("   cd claw && pnpm openclaw pairing approve telegram <CODE>")
    print()
    print("="*70)


async def main():
    """Main setup flow."""
    print("="*70)
    print("🤖 Archon AI Setup from .env")
    print("="*70)
    print()
    
    # 1. Setup Gateway config
    if not setup_gateway_config():
        print("\n❌ Setup failed")
        return 1
    
    # 2. Print summary
    print_config_summary()
    
    # 3. Create run scripts
    create_run_scripts()
    
    # 4. Test connections
    await test_connections()
    
    # 5. Print next steps
    print_next_steps()
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
