"""Unit tests for LINE Messaging API signature verification, flex cards, and event dispatch."""

import unittest
import os
import json
import hmac
import hashlib
import base64
from unittest.mock import patch, MagicMock
from src.agent.fsm_engine import ICareAgent
from src.server.line_handler import (
    verify_line_signature,
    create_welcome_flex_message,
    create_crisis_flex_message,
    handle_line_events,
    send_line_reply
)


class TestLineIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(base_dir, "data")
        cls.agent = ICareAgent(data_dir=data_dir)
        cls.secret = "mock_secret_key_123456"

    def test_signature_verification_valid(self):
        body = json.dumps({"events": []}).encode("utf-8")
        # Generate valid HMAC-SHA256
        h = hmac.new(self.secret.encode("utf-8"), body, hashlib.sha256).digest()
        valid_signature = base64.b64encode(h).decode("utf-8")

        self.assertTrue(verify_line_signature(body, valid_signature, self.secret))

    def test_signature_verification_invalid(self):
        body = json.dumps({"events": []}).encode("utf-8")
        invalid_signature = "bad_signature_string"

        self.assertFalse(verify_line_signature(body, invalid_signature, self.secret))

    def test_welcome_flex_message_schema(self):
        flex = create_welcome_flex_message()
        self.assertEqual(flex["type"], "flex")
        self.assertEqual(flex["contents"]["type"], "bubble")
        self.assertIn("Welcome", flex["altText"])
        # Check action buttons for ARC, NHI, Dorms, Course
        buttons = flex["contents"]["footer"]["contents"]
        self.assertEqual(len(buttons), 4)

    def test_crisis_flex_message_schema(self):
        state = self.agent.process_message("test_crisis", "I want to kill myself")
        flex = create_crisis_flex_message(state)
        self.assertEqual(flex["type"], "flex")
        self.assertIn("Immediate", flex["altText"])
        footer_buttons = flex["contents"]["footer"]["contents"]
        uris = [b["action"]["uri"] for b in footer_buttons]
        self.assertIn("tel:1925", uris)
        self.assertIn("tel:1955", uris)

    @patch("src.server.line_handler.send_line_reply")
    def test_handle_line_text_message(self, mock_reply):
        mock_reply.return_value = (True, None)

        events = [
            {
                "type": "message",
                "replyToken": "valid_token_123",
                "source": {"userId": "line_user_u987654"},
                "message": {
                    "type": "text",
                    "text": "What is the fee for an Alien Resident Certificate?"
                }
            }
        ]

        results = handle_line_events(events, self.agent, "mock_channel_access_token")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["type"], "message")
        self.assertEqual(results[0]["fsm_state"], "COMPLETED")
        self.assertTrue(results[0]["sent"])
        mock_reply.assert_called_once()

    @patch("src.server.line_handler.send_line_reply")
    def test_handle_line_follow_event(self, mock_reply):
        mock_reply.return_value = (True, None)

        events = [
            {
                "type": "follow",
                "replyToken": "follow_token_456",
                "source": {"userId": "line_new_friend_123"}
            }
        ]

        results = handle_line_events(events, self.agent, "mock_channel_access_token")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["type"], "follow")
        self.assertTrue(results[0]["sent"])

    @patch("src.server.line_handler.send_line_reply")
    def test_handle_line_join_group_event(self, mock_reply):
        mock_reply.return_value = (True, None)

        events = [
            {
                "type": "join",
                "replyToken": "join_token_789",
                "source": {"type": "group", "groupId": "group_room_123"}
            }
        ]

        results = handle_line_events(events, self.agent, "mock_channel_access_token")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["type"], "join")
        self.assertEqual(results[0]["user_id"], "group_room_123")
        self.assertTrue(results[0]["sent"])

    @patch("src.server.line_handler.send_line_reply")
    def test_handle_line_non_text_message(self, mock_reply):
        mock_reply.return_value = (True, None)

        events = [
            {
                "type": "message",
                "replyToken": "sticker_token_999",
                "source": {"type": "user", "userId": "user_sticker_test"},
                "message": {"type": "sticker", "packageId": "1", "stickerId": "1"}
            }
        ]

        results = handle_line_events(events, self.agent, "mock_channel_access_token")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["type"], "message")
        self.assertEqual(results[0]["msg_type"], "sticker")
        self.assertTrue(results[0]["sent"])


if __name__ == "__main__":
    unittest.main()
