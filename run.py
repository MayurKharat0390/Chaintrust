"""
run.py — ChainTrust One-Click Project Launcher
=============================================
Execute this single file to run the entire ChainTrust system:
    python run.py

What this does automatically:
1. Initializes & verifies SQLite database (`chaintrust.db`)
2. Synchronizes registered agents from `config/agents.yaml`
3. Checks local Ollama service for offline inference (`llama32-ollama-local`)
4. Starts the ChainTrust FastAPI web application & REST API
5. Automatically opens the interactive dashboard in your default browser at http://127.0.0.1:8000/
"""

import os
import sys
import time
import socket
import logging
import urllib.request
import webbrowser
import subprocess
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

BANNER = r"""
=================================================================================
    ____ _           _       _____                _   
   / ___| |__   __ _(_)_ __ |_   _| __ _   _ ___| |_ 
  | |   | '_ \ / _` | | '_ \  | || '__| | | / __| __|
  | |___| | | | (_| | | | | | | || |  | |_| \__ \ |_ 
   \____|_| |_|\__,_|_|_| |_| |_||_|   \__,_|___/\__|
   
    Autonomous AI Agent Evaluation, Cryptographic Merkle Anchoring,
    & Sybil-Resilient Hybrid Reputation Protocol (CHS)
=================================================================================
"""


def check_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a port is already open/in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def check_and_start_ollama():
    """Verify if Ollama is running for offline agent support, or attempt to start it."""
    print(" [1/4] Checking local Ollama service for offline agent...", end=" ", flush=True)
    try:
        req = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=1.5)
        if req.status == 200:
            print("OK (Ollama is online)")
            return True
    except Exception:
        pass

    # Try starting ollama serve in background if installed
    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        time.sleep(1.0)
        print("STARTED (Launched local Ollama daemon)")
        return True
    except Exception:
        print("OFFLINE (Cloud agents will run; start `ollama serve` if running offline model)")
        return False


def setup_database_and_registry():
    """Verify database schema and sync canonical agents."""
    print(" [2/4] Initializing database and syncing agents...", end=" ", flush=True)
    try:
        from chaintrust.db.session import init_db, get_session
        from chaintrust.registry.agent_registry import AgentRegistry
        from chaintrust.db.models import Agent, Task

        init_db()
        registry = AgentRegistry()
        registry.register_all()

        with get_session() as s:
            agent_count = s.query(Agent).count()
            task_count = s.query(Task).count()

        print(f"OK ({agent_count} agents registered, {task_count} tasks available)")
        return True
    except Exception as e:
        print(f"WARNING: {e}")
        return False


def open_browser(url: str, delay_seconds: float = 1.2):
    """Wait for server to start, then open user's default browser."""
    time.sleep(delay_seconds)
    print(f" [4/4] Opening dashboard at {url} in your browser...")
    try:
        webbrowser.open(url)
    except Exception as e:
        print(f" Note: Could not auto-open browser ({e}). Please navigate to {url}")


def main():
    print(BANNER)
    print(f" Project Root: {PROJECT_ROOT}")
    print(f" Python Executable: {sys.executable}\n")

    # Step 1: Check Ollama for offline demo
    check_and_start_ollama()

    # Step 2: Database setup
    setup_database_and_registry()

    port = 8000
    host = "127.0.0.1"
    url = f"http://{host}:{port}/"

    # Step 3: Check if port is already running
    if check_port_in_use(port, host):
        print(f"\n [3/4] Server is ALREADY RUNNING on {url}!")
        print(f" [4/4] Opening {url} directly in your browser...")
        webbrowser.open(url)
        print("\n" + "=" * 80)
        print(f"  ChainTrust Dashboard: {url}")
        print("  Press Ctrl+C in the active server terminal to stop.")
        print("=" * 80 + "\n")
        return

    print(f" [3/4] Starting ChainTrust FastAPI Server on {url}...")

    # Launch browser thread
    import threading
    browser_thread = threading.Thread(target=open_browser, args=(url, 1.2), daemon=True)
    browser_thread.start()

    print("\n" + "=" * 80)
    print(f"  🚀 CHAINTRUST LIVE DASHBOARD: {url}")
    print("  📋 Interactive Tabs Available:")
    print("     • 🏆 Leaderboard (with CHS Breakdown & Live Ranks)")
    print("     • ⚔️ Algorithm Comparison (CHS vs Elo vs TraceRank vs PageRank)")
    print("     • ⚡ Live Arena & 3D Holo-Chamber (Live execution & local Ollama)")
    print("     • 🛡️ Sybil Resilience Benchmark")
    print("     • 🔗 Blockchain & Merkle Audit (Zero-trust standalone verifier)")
    print("     • 📁 Task Bank & Dynamic Hardness")
    print("  ----------------------------------------------------------------------")
    print("  To stop the server at any time, press [Ctrl + C].")
    print("=" * 80 + "\n")

    import uvicorn
    try:
        uvicorn.run("chaintrust.api.main:app", host=host, port=port, log_level="warning")
    except KeyboardInterrupt:
        print("\n [!] ChainTrust server stopped cleanly. Goodbye!")


if __name__ == "__main__":
    main()
