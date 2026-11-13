"""iCare Tools Layer.

Contains external action tools for:
- Google Calendar event & deadline syncing (calendar_tool)
- Campus Webhook intake & appointment scheduling (campus_webhook_tool)
- Pre-filled email referral drafts (email_draft_tool)
- Official alphanumeric receipt emission REC-SCH-XXXX (receipt_emitter)
- Human-in-the-Loop Two-Phase Commit Gate (action_executor)
"""

from src.tools.receipt_emitter import emit_receipt
from src.tools.calendar_tool import create_calendar_event
from src.tools.campus_webhook_tool import dispatch_campus_webhook, UpstreamWebhookError
from src.tools.email_draft_tool import generate_email_draft
from src.tools.action_executor import create_action_proposal, execute_action

__all__ = [
    "emit_receipt",
    "create_calendar_event",
    "dispatch_campus_webhook",
    "UpstreamWebhookError",
    "generate_email_draft",
    "create_action_proposal",
    "execute_action",
]
