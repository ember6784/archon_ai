"""
@quant_dev_ai_bot Setup Script

Automated setup for Telegram bot integration.
"""

import os
import sys
import shutil
from pathlib import Path


def setup_openclaw_config():
    """Setup OpenClaw configuration for Telegram bot."""
    
    claw_config = Path("E:/archon_ai/claw/config/default.json5")
    
    config_content = """{
  channels: {
    telegram: {
      enabled: true,
      botToken: "7898417089:AAHaUj3Ywlsnaqr2e71RjrmJMdNUxMpdu-0",
      dmPolicy: "pairing",
    },
  },
}"""
    
    # Ensure config directory exists
    claw_config.parent.mkdir(parents=True, exist_ok=True)
    
    # Write config
    claw_config.write_text(config_content)
    print(f"[+] OpenClaw config created: {claw_config}")
    
    return claw_config


def setup_env_file():
    """Setup .env file for Archon AI."""
    
    env_path = Path("E:/archon_ai/.env")
    
    env_content = """# Archon AI Environment Configuration

# ==========================================================================
# OPENCLAW GATEWAY
# ==========================================================================
OPENCLAW_GATEWAY_URL=ws://localhost:18789
OPENCLAW_GATEWAY_TOKEN=test_token_123
OPENCLAW_GATEWAY_TIMEOUT=30

# ==========================================================================
# APPLICATION
# ==========================================================================
APP_NAME=OpenClaw Enterprise
APP_VERSION=0.1.0
ENVIRONMENT=development
DEBUG=false
LOG_LEVEL=INFO

# ==========================================================================
# CIRCUIT BREAKER
# ==========================================================================
CIRCUIT_BREAKER_ENABLED=true
CIRCUIT_BREAKER_BASE_DIR=./data/circuit_breaker

# ==========================================================================
# AUDIT
# ==========================================================================
AUDIT_ENABLED=true
AUDIT_RETENTION_DAYS=30

# ==========================================================================
# MULTI-TENANCY
# ==========================================================================
MULTI_TENANT_ENABLED=true
MAX_TENANTS=1000
"""
    
    env_path.write_text(env_content)
    print(f"[+] .env file created: {env_path}")
    
    return env_path


def print_instructions():
    """Print setup instructions."""
    
    print("\n" + "=" * 60)
    print("Setup Complete!")
    print("=" * 60)
    print("""
Next steps:

1. Start OpenClaw Gateway:
   cd E:\archon_ai\claw
   pnpm openclaw gateway --port 18789 --allow-unconfigured --token test_token_123

2. In a NEW terminal, start Archon AI:
   cd E:\archon_ai
   python run_quant_bot.py

3. Send /start to @quant_dev_ai_bot in Telegram

4. Approve pairing:
   cd E:\archon_ai\claw
   pnpm openclaw pairing approve telegram <CODE_FROM_BOT>

5. Send messages to the bot!

For testing:
- python test_gateway.py        # Test connection
- python test_end_to_end.py       # Interactive test
- python test_real_messages.py    # Listen for real messages
    """)


def main():
    """Main setup function."""
    
    print("""
    ================================================
       @quant_dev_ai_bot Setup Wizard
    ================================================
    """)
    
    # Step 1: Setup OpenClaw config
    print("Step 1: Configuring OpenClaw...")
    setup_openclaw_config()
    
    # Step 2: Setup .env file
    print("\nStep 2: Creating .env file...")
    setup_env_file()
    
    # Step 3: Print instructions
    print_instructions()
    
    print("\n✅ Setup complete!")


if __name__ == "__main__":
    main()
