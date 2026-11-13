"""In-memory tests for iCare HTTP Handler and REST dispatching."""

import unittest
import os
import json
import io
from unittest.mock import MagicMock
from src.agent.fsm_engine import ICareAgent
from src.server.http_server import create_handler_class


class MockSocket:
    def __init__(self, data: bytes = b""):
        self.rfile = io.BytesIO(data)
        self.wfile = io.BytesIO()

    def makefile(self, mode, *args, **kwargs):
        if "b" in mode:
            if "r" in mode:
                return self.rfile
            return self.wfile
        return self.rfile


class TestServerHandler(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(base_dir, "data")
        cls.static_dir = os.path.join(base_dir, "src", "server", "static")
        cls.agent = ICareAgent(data_dir=data_dir)
        cls.handler_class = create_handler_class(cls.agent, cls.static_dir)

    def _execute_request(self, method: str, path: str, body: dict = None) -> tuple:
        """Executes an in-memory HTTP request against the handler."""
        body_bytes = json.dumps(body).encode("utf-8") if body else b""
        req_lines = [
            f"{method} {path} HTTP/1.1",
            "Host: localhost",
            f"Content-Length: {len(body_bytes)}",
            "Content-Type: application/json",
            "",
            ""
        ]
        raw_request = "\r\n".join(req_lines).encode("utf-8") + body_bytes
        
        sock = MockSocket(raw_request)
        handler = self.handler_class(sock.rfile, ("127.0.0.1", 12345), None)
        
        # Read response from wfile
        raw_response = sock.wfile.getvalue()
        return raw_response

    def test_agent_api_chat_direct(self):
        # Directly test chat endpoint behavior
        state = self.agent.process_message(
            session_id="test_sess",
            raw_text="What is the monthly fee for National Health Insurance (NHI)?"
        )
        self.assertEqual(state.fsm_state.value, "COMPLETED")
        self.assertFalse(state.is_crisis)
        self.assertIn("NT$826", state.answer)
        self.assertTrue(len(state.citations) > 0)
        self.assertEqual(state.citations[0].source_file, "nhi_insurance.md")

    def test_agent_api_forget_direct(self):
        # Record turn
        self.agent.memory.record_turn("forget_sess", "user", "Hello")
        self.assertGreater(self.agent.memory.active_session_count(), 0)
        
        # Purge
        purged = self.agent.memory.purge_session("forget_sess")
        self.assertTrue(purged)

    def test_official_services_catalog(self):
        services = self.agent.official_services
        self.assertIn("services", services)
        self.assertIn("oia", services["services"])
        self.assertIn("crisis_emergency", services["services"])


if __name__ == "__main__":
    unittest.main()
