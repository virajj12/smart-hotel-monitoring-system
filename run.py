#!/usr/bin/env python3
"""
Smart Hotel Monitoring System (SHMS) - Edge Server Launcher
===========================================================
Single-command cross-platform runner for the SHMS Edge Vision Node.
Handles environment detection, preflight checks, database setup,
and boots FastAPI/Uvicorn with automatic browser launch.
"""

import os
import sys
import time
import socket
import shutil
import argparse
import threading
import webbrowser
from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).resolve().parent
os.environ.setdefault("YOLO_CONFIG_DIR", str(BASE_DIR / ".yolo"))
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"
ENV_FILE = BASE_DIR / ".env"
ENV_EXAMPLE = BASE_DIR / ".env.example"
DB_FILE = BASE_DIR / "hotel_monitoring.db"
MODEL_PT = BASE_DIR / "best.pt"
MODEL_ONNX = BASE_DIR / "best.onnx"

# Colors for terminal output
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_banner(host: str, port: int, central_url: str):
    """Prints a styled startup banner."""
    print(f"\n{CYAN}{BOLD}" + "=" * 70)
    print("   SMART HOTEL MONITORING SYSTEM (SHMS) - EDGE VISION NODE")
    print("=" * 70 + f"{RESET}\n")
    print(f"  {GREEN}[+] Status:{RESET}          Edge Engine Initializing...")
    print(f"  {GREEN}[+] Web UI:{RESET}          http://localhost:{port}")
    print(f"  {GREEN}[+] Network URL:{RESET}     http://{get_local_ip()}:{port}")
    if central_url:
        print(f"  {GREEN}[+] Central Cloud:{RESET}   {central_url}")
    else:
        print(f"  {YELLOW}[!] Central Cloud:{RESET}   Standalone Mode (CENTRAL_SERVER_URL not set)")
    print(f"  {GREEN}[+] Working Dir:{RESET}     {BASE_DIR}")
    print(f"\n{CYAN}" + "-" * 70 + f"{RESET}\n")


def get_local_ip() -> str:
    """Best-effort discovery of local LAN IP."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def preflight_checks():
    """Validates runtime prerequisites and sets up default configs."""
    # 1. Check Python version
    if sys.version_info < (3, 10):
        print(f"{YELLOW}[!] Warning: Python 3.10+ recommended. Current: {sys.version}{RESET}")

    # 2. Ensure .env exists
    if not ENV_FILE.exists():
        if ENV_EXAMPLE.exists():
            print(f"{YELLOW}[i] .env not found. Auto-creating from .env.example...{RESET}")
            shutil.copy(ENV_EXAMPLE, ENV_FILE)
            print(f"{GREEN}[✓] Created .env configuration file.{RESET}")
        else:
            print(f"{YELLOW}[!] Neither .env nor .env.example found. Creating minimal .env...{RESET}")
            ENV_FILE.write_text(
                "CAMERA_ADMIN_PASSWORD=change_this_admin_pass\n"
                "NOTIFICATION_WEBHOOK_URL=\n"
                "CENTRAL_SERVER_URL=http://localhost:3000\n"
                "EDGE_NODE_ID=edge-local-01\n"
            )

    # 3. Verify AI Model weights exist
    if MODEL_PT.exists():
        print(f"{GREEN}[✓] PyTorch YOLO Model found: {MODEL_PT.name}{RESET}")
    elif MODEL_ONNX.exists():
        print(f"{GREEN}[✓] ONNX YOLO Model found: {MODEL_ONNX.name}{RESET}")
    else:
        print(f"{YELLOW}[!] Note: Neither best.pt nor best.onnx found in root. Default pretrained weights may be used.{RESET}")

    # 4. Check Frontend build
    if not (FRONTEND_DIST / "index.html").exists():
        print(f"{YELLOW}[!] Prebuilt dashboard not found in frontend/dist/index.html.{RESET}")
        npm_bin = shutil.which("npm")
        if npm_bin:
            print(f"{CYAN}[i] Node.js/npm detected. Auto-building React dashboard...{RESET}")
            frontend_dir = BASE_DIR / "frontend"
            try:
                import subprocess
                if not (frontend_dir / "node_modules").exists():
                    print(f"{YELLOW}[i] Running npm install in frontend/...{RESET}")
                    subprocess.run(["npm", "install"], cwd=frontend_dir, check=True, shell=True)
                print(f"{YELLOW}[i] Running npm run build in frontend/...{RESET}")
                subprocess.run(["npm", "run", "build"], cwd=frontend_dir, check=True, shell=True)
                print(f"{GREEN}[✓] Frontend compiled successfully to frontend/dist!{RESET}")
            except Exception as e:
                print(f"{RED}[✗] Failed to auto-build frontend: {e}{RESET}")
        else:
            print(f"{YELLOW}[i] Node.js/npm not found. Backend will serve diagnostic setup page.{RESET}")
    else:
        print(f"{GREEN}[✓] Prebuilt React Dashboard found at frontend/dist{RESET}")


def wait_and_open_browser(url: str, port: int, timeout: int = 15):
    """Waits for the HTTP port to open, then opens the browser."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                time.sleep(0.5)
                webbrowser.open(url)
                return
        except (OSError, ConnectionRefusedError):
            time.sleep(0.3)
    # Fallback attempt
    try:
        webbrowser.open(url)
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(description="SHMS Edge Vision Server Launcher")
    parser.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"), help="Host to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")), help="Port to bind (default: 8000)")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically open the browser")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload on code change")
    args = parser.parse_args()

    # Preflight checks
    preflight_checks()

    # Read .env central server URL for banner display
    central_url = ""
    try:
        from dotenv import load_dotenv
        load_dotenv(ENV_FILE)
        central_url = os.getenv("CENTRAL_SERVER_URL", "")
    except ImportError:
        pass

    # Print banner
    print_banner(args.host, args.port, central_url)

    # Spawn browser thread if not disabled
    dashboard_url = f"http://localhost:{args.port}"
    if not args.no_browser:
        t = threading.Thread(target=wait_and_open_browser, args=(dashboard_url, args.port), daemon=True)
        t.start()

    # Import and run uvicorn
    try:
        import uvicorn
    except ImportError:
        print(f"{RED}[✗] Error: 'uvicorn' is not installed in the active Python environment.{RESET}")
        print(f"    Please run: pip install -r requirements.txt")
        sys.exit(1)

    try:
        if args.reload:
            uvicorn.run(
                "main:app",
                host=args.host,
                port=args.port,
                reload=True,
                log_level="info"
            )
        else:
            from main import app
            uvicorn.run(
                app,
                host=args.host,
                port=args.port,
                log_level="info"
            )
    except KeyboardInterrupt:
        print(f"\n{CYAN}[i] SHMS Edge Server stopped cleanly.{RESET}")


if __name__ == "__main__":
    main()
