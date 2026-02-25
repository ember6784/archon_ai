"""
Archon AI - Main Entry Point

🏛️ Enterprise AI Operating System with T0-T3 security architecture

Components:
- Gateway Bridge (OpenClaw integration)
- Event Bus (async messaging)
- State Manager (distributed state)
- RBAC (access control)
- Audit Logger (compliance)
- Execution Contract (security enforcement)
- API Server (FastAPI)
"""

import asyncio
import logging
import signal

import uvicorn
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from enterprise.config import settings
from enterprise.event_bus import EventBus, EventType
from enterprise.gateway_bridge import GatewayBridge
from enterprise.openclaw_integration import IntegrationConfig, create_secure_bridge

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(settings.data_dir / "archon.log")
    ]
)
logger = logging.getLogger(__name__)

console = Console()


class ArchonService:
    """
    Main Archon AI service orchestrator.

    Manages all components and handles graceful shutdown.
    """

    def __init__(self):
        self.event_bus = EventBus(persist_events=settings.audit_enabled)

        # Create integration config for secure bridge
        integration_config = IntegrationConfig()
        integration_config.ws_url = settings.openclaw_gateway_url
        integration_config.auth_token = settings.openclaw_gateway_token
        integration_config.enable_audit = settings.audit_enabled
        integration_config.kernel_environment = settings.environment
        integration_config.enable_circuit_breaker = settings.circuit_breaker_enabled

        # Use secure bridge with kernel validation
        self.gateway_bridge = create_secure_bridge(
            integration_config=integration_config,
            event_bus=self.event_bus,
        )
        self._running = False
        self._shutdown_event = asyncio.Event()

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, initiating shutdown...")
        self._shutdown_event.set()

    async def start(self):
        """Start all components."""
        if self._running:
            logger.warning("Service already running")
            return

        self._running = True

        # Create data directories
        self._create_directories()

        # Start event bus
        await self.event_bus.start()
        logger.info("Event bus started")

        # Start gateway bridge
        await self.gateway_bridge.start()
        logger.info("Gateway bridge started")

        # Subscribe to events for monitoring
        self.event_bus.subscribe(
            EventType.PERMISSION_DENIED,
            self._on_permission_denied
        )
        self.event_bus.subscribe(
            EventType.SIEGE_MODE_ACTIVATED,
            self._on_siege_mode_activated
        )

        self._print_banner()

    async def stop(self):
        """Stop all components gracefully."""
        if not self._running:
            return

        logger.info("Shutting down Archon AI service...")

        # Stop gateway bridge
        await self.gateway_bridge.stop()

        # Stop event bus
        await self.event_bus.stop()

        self._running = False
        logger.info("Archon AI service stopped")

    async def run(self):
        """Run the service until shutdown."""
        await self.start()

        try:
            # Wait for shutdown signal
            await self._shutdown_event.wait()
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()

    def _create_directories(self):
        """Create required data directories."""
        dirs = [
            settings.data_dir,
            settings.audit_dir,
            settings.circuit_breaker_dir,
        ]

        for dir_path in dirs:
            dir_path.mkdir(parents=True, exist_ok=True)

    def _print_banner(self):
        """Print startup banner."""
        console.print(Panel.fit(
            "[bold cyan]Archon AI[/bold cyan] [dim](Enterprise)[/dim]\n"
            f"[dim]Version {settings.app_version}[/dim]\n"
            f"[green]Environment: {settings.environment}[/green]",
            border_style="cyan"
        ))

        # Print component status
        table = Table(title="Components", show_header=True)
        table.add_column("Component", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Details", style="dim")

        table.add_row(
            "Event Bus",
            "[+] Running",
            f"Subscribers: {len(self.event_bus._subscribers)}"
        )
        table.add_row(
            "Gateway Bridge",
            "[+] Running",
            f"WS URL: {settings.openclaw_gateway_url}"
        )
        table.add_row(
            "Execution Contract",
            "[+] Ready",
            "4 profiles: GREEN/AMBER/RED/BLACK"
        )
        table.add_row(
            "Circuit Breaker",
            "[+] Enabled" if settings.circuit_breaker_enabled else "[-] Disabled",
            f"Base: {settings.circuit_breaker_base_dir}"
        )
        table.add_row(
            "Audit",
            "[+] Enabled" if settings.audit_enabled else "[-] Disabled",
            f"Retention: {settings.audit_retention_days} days"
        )
        table.add_row(
            "Multi-tenant",
            "[+] Enabled" if settings.multi_tenant_enabled else "[-] Disabled",
            f"Max: {settings.max_tenants} tenants"
        )

        console.print(table)

    async def _on_permission_denied(self, event):
        """Handle permission denied events."""
        logger.warning(
            f"Permission denied: user={event.user_id} "
            f"data={event.data}"
        )

    async def _on_siege_mode_activated(self, event):
        """Handle siege mode activation."""
        logger.critical(
            f"SIEGE MODE ACTIVATED: {event.data}"
        )


async def main():
    """Main entry point."""
    service = ArchonService()

    try:
        await service.run()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


def run_api():
    """
    Run the FastAPI server.

    This is the entry point for the API service.
    """
    # TODO: Create FastAPI app
    console.print("[yellow]API server not yet implemented[/yellow]")
    console.print("[dim]Use 'python -m enterprise.main' for the service[/dim]")


if __name__ == "__main__":
    # Check if --api flag is present
    if "--api" in sys.argv:
        run_api()
    else:
        asyncio.run(main())
