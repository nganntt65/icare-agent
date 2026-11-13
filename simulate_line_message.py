#!/usr/bin/env python3
"""LINE Webhook Simulator for Local Development & Testing.

Allows testing inbound LINE webhook events (text messages, follow greetings,
and crisis events) against the local iCare server without requiring an external tunnel.

Usage:
    python3 simulate_line_message.py --text "My ARC expires in 3 days"
    python3 simulate_line_message.py --text "Làm thế nào để gia hạn thẻ cư trú?"
    python3 simulate_line_message.py --follow
    python3 simulate_line_message.py --crisis
"""

import sys
import os
import json
import argparse
import hmac
import hashlib
import base64
import urllib.request
import urllib.error


def send_simulated_event(event_dict: dict, server_url: str = "http://127.0.0.1:8000/api/webhook/line", secret: str = ""):
    payload = {"events": [event_dict], "destination": "U1234567890abcdef"}
    body_bytes = json.dumps(payload).encode("utf-8")

    headers = {"Content-Type": "application/json"}

    if secret:
        h = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).digest()
        signature = base64.b64encode(h).decode("utf-8")
        headers["X-Line-Signature"] = signature

    req = urllib.request.Request(server_url, data=body_bytes, headers=headers, method="POST")

    print(f"📡 Sending simulated LINE event to {server_url}...")
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print(f"✅ Response ({resp.status}):")
            print(json.dumps(data, indent=2, ensure_ascii=False))
    except urllib.error.HTTPError as e:
        print(f"❌ HTTP Error {e.code}: {e.read().decode('utf-8')}")
    except Exception as e:
        print(f"❌ Connection Error: {str(e)}")
        print("💡 Ensure the server is running: python3 run.py --port 8000")


def load_env():
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k and k not in os.environ:
                        os.environ[k] = v


def main():
    load_env()
    parser = argparse.ArgumentParser(description="Simulate LINE Webhook Inbound Events")
    parser.add_argument("--text", type=str, help="Text message to send from student")
    parser.add_argument("--follow", action="store_true", help="Simulate student adding bot as friend")
    parser.add_argument("--join", action="store_true", help="Simulate bot added to group")
    parser.add_argument("--crisis", action="store_true", help="Simulate crisis self-harm distress message")
    parser.add_argument("--postback", type=str, help="Simulate LINE postback data (e.g. 'action=confirm&proposal_id=PROP-CAL-1234&token=abcd')")
    parser.add_argument("--url", type=str, default="http://127.0.0.1:8000/api/webhook/line", help="Webhook endpoint URL")
    parser.add_argument("--secret", type=str, default=os.environ.get("LINE_CHANNEL_SECRET", ""), help="LINE Channel Secret")
    parser.add_argument("--user-id", type=str, default="U_mock_student_line_id", help="Simulated LINE User ID")
    args = parser.parse_args()

    if args.postback:
        event = {
            "type": "postback",
            "replyToken": "mock_reply_token_" + hashlib.md5(args.postback.encode()).hexdigest()[:8],
            "source": {"userId": args.user_id, "type": "user"},
            "postback": {"data": args.postback},
            "timestamp": 1727960000000,
            "mode": "active"
        }
    elif args.follow:
        event = {
            "type": "follow",
            "replyToken": "mock_reply_token_" + hashlib.md5(b"follow").hexdigest()[:8],
            "source": {"userId": args.user_id, "type": "user"},
            "timestamp": 1727960000000,
            "mode": "active"
        }
    elif args.join:
        event = {
            "type": "join",
            "replyToken": "mock_reply_token_" + hashlib.md5(b"join").hexdigest()[:8],
            "source": {"groupId": "G_mock_group_line_id", "type": "group"},
            "timestamp": 1727960000000,
            "mode": "active"
        }
    elif args.crisis:
        event = {
            "type": "message",
            "replyToken": "mock_reply_token_" + hashlib.md5(b"crisis").hexdigest()[:8],
            "source": {"userId": args.user_id, "type": "user"},
            "message": {"id": "msg_002", "type": "text", "text": "I feel so hopeless, alone, and want to end my life."},
            "timestamp": 1727960000000,
            "mode": "active"
        }
    else:
        text_content = args.text or "My ARC expires in three days. What documents do I need from the school?"
        event = {
            "type": "message",
            "replyToken": "mock_reply_token_" + hashlib.md5(text_content.encode()).hexdigest()[:8],
            "source": {"userId": args.user_id, "type": "user"},
            "message": {"id": "msg_001", "type": "text", "text": text_content},
            "timestamp": 1727960000000,
            "mode": "active"
        }

    send_simulated_event(event, server_url=args.url, secret=args.secret)


if __name__ == "__main__":
    main()
