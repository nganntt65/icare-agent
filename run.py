#!/usr/bin/env python3
"""iCare Agent Server Launcher.

Usage:
    python3 run.py [--port 8000] [--host 127.0.0.1]
"""

import os
import sys
import argparse

# Add project root to sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.server.http_server import run_server


def load_env(env_path: str):
    """Loads environment variables from .env file if present."""
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k and k not in os.environ:
                        os.environ[k] = v


def main():
    load_env(os.path.join(BASE_DIR, ".env"))
    parser = argparse.ArgumentParser(description="iCare Agentic AI Navigator Server")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host interface (default: 127.0.0.1)")
    parser.add_argument("--data-dir", type=str, default=os.path.join(BASE_DIR, "data"), help="Path to knowledge directory")
    args = parser.parse_args()

    print("=" * 70)
    print("🇹🇼  iCare: A Cross-Cultural Agentic AI Navigator (Track 1 MVP)")
    print("    Team MaVi | Campus Administration & Service Processes")
    print("=" * 70)
    print(f"📁 Knowledge Directory: {args.data_dir}")
    print(f"🌐 Server Starting at: http://{args.host}:{args.port}")
    print("=" * 70)

    run_server(data_dir=args.data_dir, port=args.port, host=args.host)


if __name__ == "__main__":
    main()
