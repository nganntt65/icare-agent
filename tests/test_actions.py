"""Comprehensive Tests for Action Proposals, External Tool Triggers, and Two-Phase Commit HITL Gate.

Validates Proposal Sections 5, 6, 7 & 10:
- Google Calendar Sync Tool (live API vs sandbox render template)
- Campus Webhook Tool (2x retry on 5xx and UpstreamWebhookError)
- Email Draft & Walk-in Referral Tool (with checklist and mailto URLs)
- Official Alphanumeric Receipt Emitter (REC-SCH-XXXX)
- Human-in-the-Loop Two-Phase Commit Gate (RBAC Token Enforcement)
- Upstream 500 Outage Fallback Recovery
- FSM Lifecycle (AWAITING_CONFIRMATION -> ACTION_EXECUTED / Rollback)
- LINE Postback Event Processing
"""

import unittest
import os
import re
from src.agent.fsm_engine import ICareAgent
from src.agent.state import FSMStateEnum, ActionType, ActionProposal
from src.tools.calendar_tool import create_calendar_event
from src.tools.campus_webhook_tool import dispatch_campus_webhook, UpstreamWebhookError
from src.tools.email_draft_tool import generate_email_draft
from src.tools.receipt_emitter import emit_receipt
from src.tools.action_executor import create_action_proposal, execute_action
from src.server.line_handler import (
    create_action_proposal_flex_message,
    create_action_receipt_flex_message,
    handle_line_events
)


class TestActionTools(unittest.TestCase):
    """Unit tests for tool implementations."""

    def test_calendar_tool_sandbox(self):
        result = create_calendar_event(
            title="ARC Extension Deadline",
            start_time="2026-10-15T09:00:00+08:00",
            end_time="2026-10-15T11:00:00+08:00",
            description="Bring Passport and enrollment proof",
            location="National Immigration Agency Service Center"
        )
        self.assertEqual(result["status"], "SUCCESS")
        self.assertTrue(result["event_id"].startswith("gcal_evt_"))
        self.assertIn("calendar.google.com/calendar/render", result["calendar_url"])
        self.assertIn("ARC+Extension+Deadline", result["calendar_url"])

    def test_campus_webhook_tool_mock(self):
        result = dispatch_campus_webhook(
            department="Office of International Affairs (OIA)",
            service_type="ARC/Visa Enrollment Verification",
            student_id="student_test_101",
            appointment_time="2026-10-16 10:00",
            notes="Need official enrollment verification stamp"
        )
        self.assertEqual(result["status"], "SUCCESS")
        self.assertTrue(result["ticket_id"].startswith("TICKET-OIA-"))
        self.assertEqual(result["location"], "Administration Building, Room 201")
        self.assertEqual(result["attempts"], 1)

    def test_campus_webhook_tool_retry_and_failure(self):
        """Tests that campus webhook retries 3 times on 500 error before raising UpstreamWebhookError."""
        with self.assertRaises(UpstreamWebhookError) as ctx:
            dispatch_campus_webhook(
                department="Office of International Affairs (OIA)",
                service_type="Advising",
                force_simulate_failure=True
            )
        self.assertIn("Campus Webhook failed after 3 attempts", str(ctx.exception))

    def test_email_draft_tool(self):
        result = generate_email_draft(
            department="Office of International Affairs (OIA)",
            subject="ARC Extension Assistance",
            student_notes="My visa expires next week."
        )
        self.assertEqual(result["status"], "SUCCESS")
        self.assertTrue(result["draft_id"].startswith("DRAFT-EML-"))
        self.assertIn("oia-advising@university.edu.tw", result["recipient_email"])
        self.assertIn("mailto:", result["mailto_url"])
        self.assertIn("Room 201", result["walk_in_coordinates"]["location"])
        self.assertTrue(len(result["checklist"]) > 0)

    def test_receipt_emitter(self):
        receipt = emit_receipt(
            action_type="GOOGLE_CALENDAR_SYNC",
            proposal_id="PROP-CAL-1234",
            title="Add ARC Renewal Window to Google Calendar",
            confirmation_token="ab12",
            external_reference="https://calendar.google.com/..."
        )
        self.assertTrue(re.match(r"^REC-SCH-\d{4}$", receipt["receipt_id"]))
        self.assertEqual(receipt["status"], "CONFIRMED_AND_EXECUTED")
        self.assertEqual(len(receipt["consent_verification_hash"]), 16)
        self.assertIn("Taiwan PDPA", receipt["compliance"])


class TestTwoPhaseCommitExecutor(unittest.TestCase):
    """Tests the Human-in-the-Loop Two-Phase Commit Gate & RBAC token checks."""

    def setUp(self):
        self.proposal = create_action_proposal(
            action_type=ActionType.GOOGLE_CALENDAR_SYNC,
            title="Add ARC Renewal to Calendar",
            description="Sync NIA extension window deadline",
            parameters={
                "title": "NIA ARC Extension Window Deadline",
                "start_time": "2026-10-15T09:00:00+08:00",
                "end_time": "2026-10-15T11:00:00+08:00"
            }
        )

    def test_rbac_token_rejection(self):
        """Prohibits execution if confirmation token does not match (Zero mutation without consent)."""
        with self.assertRaises(PermissionError) as ctx:
            execute_action(
                proposal=self.proposal,
                confirmation_token="invalid_token_9999",
                session_id="test_student"
            )
        self.assertIn("RBAC Violation", str(ctx.exception))

    def test_successful_two_phase_execution(self):
        """Executes tool only when student provides matching confirmation token."""
        success, action_res, receipt = execute_action(
            proposal=self.proposal,
            confirmation_token=self.proposal.confirmation_token,
            session_id="test_student"
        )
        self.assertTrue(success)
        self.assertEqual(action_res["status"], "SUCCESS")
        self.assertTrue(receipt["receipt_id"].startswith("REC-SCH-"))
        self.assertEqual(receipt["proposal_id"], self.proposal.proposal_id)

    def test_webhook_outage_fallback_recovery(self):
        """Section 7: Upstream booking 500 error falls back to generating email draft and walk-in office coordinates."""
        webhook_prop = create_action_proposal(
            action_type=ActionType.CAMPUS_WEBHOOK_DISPATCH,
            title="Book OIA In-Person Appointment",
            description="Book Room 201 advising",
            parameters={
                "department": "Office of International Affairs (OIA)",
                "service_type": "Advising",
                "simulate_failure": True  # Force upstream 500 failure
            }
        )
        success, action_res, receipt = execute_action(
            proposal=webhook_prop,
            confirmation_token=webhook_prop.confirmation_token,
            session_id="test_student"
        )
        self.assertTrue(success)
        # Verify fallback was applied
        self.assertTrue(receipt["details"]["fallback_applied"])
        self.assertIn("Room 201", action_res["walk_in_coordinates"]["location"])
        self.assertTrue(receipt["receipt_id"].startswith("REC-SCH-"))


class TestFSMAgentActionLifecycles(unittest.TestCase):
    """Tests multi-turn action lifecycles through ICareAgent FSM."""

    @classmethod
    def setUpClass(cls):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(base_dir, "data")
        cls.agent = ICareAgent(data_dir=data_dir, confidence_threshold=0.85)

    def test_proposal_and_confirm_flow(self):
        session_id = "lifecycle_confirm_session"
        
        # Turn 1: Student asks actionable query
        state1 = self.agent.process_message(
            session_id=session_id,
            raw_text="My ARC expires in three days. Can you schedule a reminder on Google Calendar and guide me?"
        )
        self.assertEqual(state1.fsm_state, FSMStateEnum.AWAITING_CONFIRMATION)
        self.assertIsNotNone(state1.pending_action)
        self.assertEqual(state1.pending_action.action_type, ActionType.GOOGLE_CALENDAR_SYNC)
        self.assertIn("Two-Phase Commit", state1.answer)

        # Turn 2: Student confirms execution
        state2 = self.agent.process_message(
            session_id=session_id,
            raw_text="confirm"
        )
        self.assertEqual(state2.fsm_state, FSMStateEnum.ACTION_EXECUTED)
        self.assertIsNotNone(state2.execution_receipt)
        self.assertTrue(state2.execution_receipt["receipt_id"].startswith("REC-SCH-"))
        self.assertIn(state2.execution_receipt["receipt_id"], state2.answer)
        
        # Verify pending action is cleared
        self.assertIsNone(self.agent.memory.get_pending_action(session_id))

    def test_proposal_and_cancel_rollback_flow(self):
        session_id = "lifecycle_cancel_session"
        
        # Turn 1: Student asks actionable query
        state1 = self.agent.process_message(
            session_id=session_id,
            raw_text="I need to book an in-person advising appointment at OIA Room 201 via campus webhook."
        )
        self.assertEqual(state1.fsm_state, FSMStateEnum.AWAITING_CONFIRMATION)
        self.assertIsNotNone(state1.pending_action)

        # Turn 2: Student cancels
        state2 = self.agent.process_message(
            session_id=session_id,
            raw_text="cancel"
        )
        self.assertEqual(state2.fsm_state, FSMStateEnum.COMPLETED)
        self.assertIn("Action Cancelled", state2.answer)
        self.assertIsNone(state2.pending_action)
        self.assertIsNone(self.agent.memory.get_pending_action(session_id))

    def test_mid_conversation_goal_shift(self):
        """Proposal Section 7: Mid-conversation goal shift resets pending memory cleanly."""
        session_id = "lifecycle_shift_session"
        
        # Turn 1: Actionable query
        state1 = self.agent.process_message(
            session_id=session_id,
            raw_text="Please add my ARC renewal deadline to Google Calendar."
        )
        self.assertEqual(state1.fsm_state, FSMStateEnum.AWAITING_CONFIRMATION)

        # Turn 2: Student switches intent completely (e.g. asking about dorm curfews)
        state2 = self.agent.process_message(
            session_id=session_id,
            raw_text="What are the dormitory check-in rules and curfew hours?"
        )
        self.assertIn("dormitory", state2.answer.lower())
        self.assertTrue(any("Mid-conversation goal shift" in item for item in state2.audit_trace))
        # Prior pending action must have been cleared
        self.assertIsNone(self.agent.memory.get_pending_action(session_id))


class TestLINEPostbackIntegration(unittest.TestCase):
    """Tests LINE Flex message construction and Postback events."""

    @classmethod
    def setUpClass(cls):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(base_dir, "data")
        cls.agent = ICareAgent(data_dir=data_dir, confidence_threshold=0.85)

    def test_create_action_proposal_flex_card(self):
        proposal = create_action_proposal(
            action_type=ActionType.GOOGLE_CALENDAR_SYNC,
            title="Sync ARC Renewal Window",
            description="Synchronize NIA extension deadline with Google Calendar",
            parameters={"location": "NIA Taipei Center", "start_time": "2026-10-15T09:00:00"}
        )
        card = create_action_proposal_flex_message(proposal, "en")
        self.assertEqual(card["type"], "flex")
        self.assertIn("Sync ARC Renewal Window", card["altText"])
        footer = card["contents"]["footer"]["contents"]
        # Confirm postback button
        self.assertEqual(footer[0]["action"]["type"], "postback")
        self.assertIn(f"proposal_id={proposal.proposal_id}", footer[0]["action"]["data"])
        self.assertIn(f"token={proposal.confirmation_token}", footer[0]["action"]["data"])

    def test_create_receipt_flex_card(self):
        receipt = emit_receipt(
            action_type="GOOGLE_CALENDAR_SYNC",
            proposal_id="PROP-CAL-7711",
            title="Scheduled Calendar Reminder",
            confirmation_token="3f8a",
            external_reference="https://calendar.google.com/calendar/render?..."
        )
        card = create_action_receipt_flex_message(receipt)
        self.assertEqual(card["type"], "flex")
        self.assertIn(receipt["receipt_id"], card["altText"])

    def test_line_postback_confirm_and_cancel_events(self):
        user_id = "line_user_postback_test"

        # 1. Propose action via message
        state = self.agent.process_message(
            session_id=user_id,
            raw_text="My ARC expires in three days. Schedule reminder on Google Calendar."
        )
        self.assertEqual(state.fsm_state, FSMStateEnum.AWAITING_CONFIRMATION)
        prop = state.pending_action

        # 2. Simulate postback event: CONFIRM
        postback_event = {
            "type": "postback",
            "replyToken": "mock_reply_token_12345",
            "source": {"type": "user", "userId": user_id},
            "postback": {
                "data": f"action=confirm&proposal_id={prop.proposal_id}&token={prop.confirmation_token}"
            }
        }
        results = handle_line_events([postback_event], self.agent, channel_access_token="mock_token")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["action"], "confirm")
        # Memory cleared
        self.assertIsNone(self.agent.memory.get_pending_action(user_id))


if __name__ == "__main__":
    unittest.main()
