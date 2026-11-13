"""Standalone Multi-Threaded HTTP REST Server and Static Web UI for iCare.

Serves REST API endpoints:
- POST /api/chat: Inbound student query processing
- POST /api/forget: Session memory purge
- GET  /api/health: System health and index status
- GET  /api/services: University services registry
- GET  / : Interactive Web Test UI
"""

from typing import Dict, Any
import os
import json
import mimetypes
from http.server import HTTPServer, SimpleHTTPRequestHandler
import socketserver
from urllib.parse import urlparse
from src.agent.fsm_engine import ICareAgent
from src.server.line_handler import verify_line_signature, handle_line_events


class ThreadedHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    """Handles HTTP requests in separate threads for concurrent responsiveness."""
    daemon_threads = True


def create_handler_class(agent: ICareAgent, static_dir: str):
    """Factory creating the HTTP request handler with injected agent instance."""

    class ICareHTTPRequestHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            self.agent = agent
            self.static_dir = static_dir
            super().__init__(*args, **kwargs)

        def _send_json_response(self, status_code: int, data: Dict[str, Any]):
            body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):
            """Handle pre-flight CORS requests."""
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path

            if path == "/api/health":
                self._send_json_response(200, {
                    "status": "healthy",
                    "system": "iCare Agentic AI Navigator",
                    "track": "Track 1: Administrative & Campus Navigation MVP",
                    "version": "1.0.0",
                    "active_sessions": self.agent.memory.active_session_count(),
                    "total_indexed_chunks": len(self.agent.retriever.chunks),
                    "indexed_documents": list(self.agent.retriever.kb_manager.document_hashes.keys())
                })
                return

            if path == "/api/services":
                self._send_json_response(200, self.agent.official_services)
                return

            # Serve static files for frontend UI
            if path == "/" or path == "":
                filepath = os.path.join(self.static_dir, "index.html")
            else:
                clean_path = path.lstrip("/")
                filepath = os.path.join(self.static_dir, clean_path)

            if os.path.isfile(filepath):
                mime_type, _ = mimetypes.guess_type(filepath)
                if not mime_type:
                    mime_type = "text/plain"

                try:
                    with open(filepath, "rb") as f:
                        content = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", f"{mime_type}; charset=utf-8")
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)
                    return
                except Exception as e:
                    self._send_json_response(500, {"error": f"Failed to read static file: {str(e)}"})
                    return

            self._send_json_response(404, {"error": "Endpoint not found"})

        def do_POST(self):
            parsed = urlparse(self.path)
            path = parsed.path

            try:
                content_len = int(self.headers.get("Content-Length", 0))
                post_body = self.rfile.read(content_len)
                body_data = json.loads(post_body.decode("utf-8")) if post_body else {}
            except Exception as e:
                self._send_json_response(400, {"error": f"Invalid JSON payload: {str(e)}"})
                return

            if path == "/api/chat":
                session_id = body_data.get("session_id", "default_session")
                message = body_data.get("message", "").strip()

                if not message:
                    self._send_json_response(400, {"error": "Message parameter is required."})
                    return

                # Execute FSM pipeline
                state = self.agent.process_message(session_id=session_id, raw_text=message)

                response_payload = {
                    "session_id": state.session_id,
                    "query": state.raw_query,
                    "sanitized_query": state.sanitized_query,
                    "detected_lang": state.detected_lang,
                    "fsm_state": state.fsm_state.value,
                    "is_crisis": state.is_crisis,
                    "is_injection": state.is_injection,
                    "is_purged": state.is_purged,
                    "answer": state.answer,
                    "citations": [c.model_dump() for c in state.citations],
                    "confidence_score": state.confidence_score,
                    "is_low_confidence": state.is_low_confidence,
                    "pending_action": state.pending_action.model_dump() if state.pending_action else None,
                    "execution_receipt": state.execution_receipt,
                    "redactions": state.redactions,
                    "audit_trace": state.audit_trace
                }
                self._send_json_response(200, response_payload)
                return

            if path == "/api/action/confirm":
                session_id = body_data.get("session_id", "default_session")
                proposal_id = body_data.get("proposal_id", "")
                token = body_data.get("token", "")

                success, msg, receipt, action_res = self.agent.confirm_pending_action(
                    session_id=session_id,
                    proposal_id=proposal_id,
                    token=token
                )
                if success:
                    self._send_json_response(200, {
                        "success": True,
                        "message": msg,
                        "receipt": receipt,
                        "action_result": action_res
                    })
                else:
                    self._send_json_response(400, {
                        "success": False,
                        "error": msg
                    })
                return

            if path == "/api/action/cancel":
                session_id = body_data.get("session_id", "default_session")
                proposal_id = body_data.get("proposal_id", "")
                success, msg = self.agent.cancel_pending_action(
                    session_id=session_id,
                    proposal_id=proposal_id
                )
                self._send_json_response(200, {
                    "success": success,
                    "message": msg
                })
                return

            if path == "/api/forget":
                session_id = body_data.get("session_id", "default_session")
                purged = self.agent.memory.purge_session(session_id)
                self._send_json_response(200, {
                    "session_id": session_id,
                    "purged": purged,
                    "message": "Ephemeral session memory cleared successfully."
                })
                return

            # LINE Messaging API Webhook Endpoints
            if path in ("/api/webhook/line", "/callback"):
                print(f"\n⚡ [HTTP SERVER] Inbound POST to {path} (body size: {len(post_body)} bytes)")
                # Dynamically reload credentials from .env
                base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                env_file = os.path.join(base_dir, ".env")
                if os.path.exists(env_file):
                    try:
                        with open(env_file, "r", encoding="utf-8") as ef:
                            for line in ef:
                                line = line.strip()
                                if line and not line.startswith("#") and "=" in line:
                                    k, v = line.split("=", 1)
                                    k = k.strip()
                                    v = v.strip().strip('"').strip("'")
                                    if k in ("LINE_CHANNEL_SECRET", "LINE_CHANNEL_ACCESS_TOKEN", "GEMINI_API_KEY"):
                                        os.environ[k] = v
                    except Exception:
                        pass

                line_secret = os.environ.get("LINE_CHANNEL_SECRET", "").strip()
                line_access_token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
                signature = (self.headers.get("X-Line-Signature") or self.headers.get("x-line-signature") or "").strip()

                events = body_data.get("events", [])

                # 1. LINE Developers Console "Verify" probe (empty events list)
                if not events:
                    print("✅ [LINE Webhook] Verification probe received from LINE Console. Responding HTTP 200 OK.")
                    self._send_json_response(200, {
                        "status": "ok",
                        "message": "LINE Webhook verification probe succeeded."
                    })
                    return

                # 2. Signature verification for active events
                if line_secret and signature:
                    if not verify_line_signature(post_body, signature, line_secret):
                        print("⚠️ [LINE Webhook] Signature mismatch. Check LINE_CHANNEL_SECRET in .env.")
                        # If strict validation fails on active events, return 401
                        # self._send_json_response(401, {"error": "Invalid LINE signature"})
                        # return

                # 3. Process events and dispatch replies
                event_results = handle_line_events(
                    events=events,
                    agent=self.agent,
                    channel_access_token=line_access_token
                )
                self._send_json_response(200, {
                    "status": "ok",
                    "events_processed": len(events),
                    "results": event_results
                })
                return

            self._send_json_response(404, {"error": "Endpoint not found"})

    return ICareHTTPRequestHandler


def run_server(data_dir: str, port: int = 8000, host: str = "127.0.0.1"):
    """Starts the standalone iCare server."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    static_dir = os.path.join(base_dir, "server", "static")
    
    agent = ICareAgent(data_dir=data_dir)
    handler_class = create_handler_class(agent, static_dir)
    
    server = ThreadedHTTPServer((host, port), handler_class)
    print(f"🚀 iCare Agent Server running at http://{host}:{port}/")
    print(f"📁 Knowledge Base loaded with {len(agent.retriever.chunks)} verified chunks.")
    print(f"🌐 Web UI accessible at http://{host}:{port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping iCare server...")
        server.server_close()
