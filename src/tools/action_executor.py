"""Human-in-the-Loop Two-Phase Commit Action Executor.

Enforces:
1. RBAC & Confirmation Token verification: No external API execution allowed without student confirmation token.
2. Two-Phase Commit Gate: Guarantees zero mutation without explicit user consent.
3. Upstream Failure Recovery: If campus booking API is down (500 error after 2 retries),
   automatically falls back to generating pre-filled email draft and walk-in coordinates.
4. Alphanumeric Receipt Emission: Emits official REC-SCH-XXXX receipt upon completion.
"""

from typing import Dict, Any, Tuple
import secrets
from datetime import datetime, timezone
from src.agent.state import ActionProposal, ActionType
from src.tools.receipt_emitter import emit_receipt
from src.tools.calendar_tool import create_calendar_event
from src.tools.campus_webhook_tool import dispatch_campus_webhook, UpstreamWebhookError
from src.tools.email_draft_tool import generate_email_draft


def create_action_proposal(
    action_type: ActionType,
    title: str,
    description: str,
    parameters: Dict[str, Any]
) -> ActionProposal:
    """Prepares an ephemeral action proposal with unique ID and confirmation token.
    
    Phase 1 of Two-Phase Commit: Safe, no external side effects or state mutations.
    """
    prefix = {
        ActionType.GOOGLE_CALENDAR_SYNC: "PROP-CAL",
        ActionType.CAMPUS_WEBHOOK_DISPATCH: "PROP-WH",
        ActionType.EMAIL_INTAKE_DRAFT: "PROP-EML"
    }.get(action_type, "PROP-ACT")

    # Cryptographically secure 4-hex confirmation token
    token = secrets.token_hex(2)  # e.g. "a3b9"
    token_num = secrets.randbelow(9000) + 1000
    proposal_id = f"{prefix}-{token_num}"
    now_iso = datetime.now(timezone.utc).isoformat()

    return ActionProposal(
        proposal_id=proposal_id,
        action_type=action_type,
        title=title,
        description=description,
        parameters=parameters,
        confirmation_token=token,
        status="PENDING_CONFIRMATION",
        created_at=now_iso
    )


def execute_action(
    proposal: ActionProposal,
    confirmation_token: str,
    session_id: str = ""
) -> Tuple[bool, Dict[str, Any], Dict[str, Any]]:
    """Phase 2 of Two-Phase Commit: Executes action after strict token validation.
    
    Args:
        proposal: The ActionProposal object.
        confirmation_token: Token provided by user during postback/confirmation.
        session_id: Optional student session ID.
        
    Returns:
        Tuple of (success_boolean, execution_result_dict, official_receipt_dict)
        
    Raises:
        PermissionError: If confirmation_token does not match proposal.confirmation_token.
    """
    # -------------------------------------------------------------
    # 1. RBAC & TOKEN VALIDATION GATE
    # -------------------------------------------------------------
    clean_token = (confirmation_token or "").strip().lower()
    expected_token = proposal.confirmation_token.strip().lower()

    if not clean_token or clean_token != expected_token:
        raise PermissionError(
            f"RBAC Violation: Confirmation token mismatch. Expected '{expected_token}', got '{clean_token}'. "
            "Action execution denied under Taiwan PDPA Two-Phase Commit policy."
        )

    # -------------------------------------------------------------
    # 2. DISPATCH TO CORRESPONDING TOOL
    # -------------------------------------------------------------
    p = proposal.parameters
    action_result = {}
    external_ref = ""
    fallback_applied = False

    if proposal.action_type == ActionType.GOOGLE_CALENDAR_SYNC:
        action_result = create_calendar_event(
            title=p.get("title", proposal.title),
            start_time=p.get("start_time", "2026-10-15T09:00:00+08:00"),
            end_time=p.get("end_time", "2026-10-15T11:00:00+08:00"),
            description=p.get("description", proposal.description),
            location=p.get("location", "National Immigration Agency Service Center")
        )
        external_ref = action_result.get("calendar_url", action_result.get("event_id", ""))

    elif proposal.action_type == ActionType.CAMPUS_WEBHOOK_DISPATCH:
        try:
            action_result = dispatch_campus_webhook(
                department=p.get("department", "Office of International Affairs (OIA)"),
                service_type=p.get("service_type", "In-Person Advising Intake"),
                student_id=session_id or "international_student",
                appointment_time=p.get("appointment_time", "Walk-in Slot (Mon-Fri 09:00-17:00)"),
                notes=p.get("notes", proposal.description),
                force_simulate_failure=p.get("simulate_failure", False)
            )
            external_ref = action_result.get("ticket_id", "")
        except UpstreamWebhookError as err:
            # Automatic Fallback Recovery: Upstream 500/timeout -> generate email draft & walk-in coordinates
            print(f"⚠️ [Tool Recovery] Upstream campus booking endpoint down: {str(err)}. Applying walk-in fallback...")
            fallback_result = generate_email_draft(
                department=p.get("department", "Office of International Affairs (OIA)"),
                subject=f"[Fallback Walk-in Referral] {proposal.title}",
                student_notes=p.get("notes", proposal.description),
                is_fallback=True
            )
            action_result = fallback_result
            external_ref = fallback_result.get("draft_id", "")
            fallback_applied = True

    elif proposal.action_type == ActionType.EMAIL_INTAKE_DRAFT:
        action_result = generate_email_draft(
            department=p.get("department", "Office of International Affairs (OIA)"),
            subject=p.get("subject", proposal.title),
            student_notes=p.get("notes", proposal.description),
            is_fallback=False
        )
        external_ref = action_result.get("mailto_url", action_result.get("draft_id", ""))

    else:
        raise ValueError(f"Unsupported action type: {proposal.action_type}")

    # -------------------------------------------------------------
    # 3. ISSUE OFFICIAL ALPHANUMERIC RECEIPT (REC-SCH-XXXX)
    # -------------------------------------------------------------
    receipt = emit_receipt(
        action_type=proposal.action_type.value,
        proposal_id=proposal.proposal_id,
        title=proposal.title,
        confirmation_token=confirmation_token,
        external_reference=external_ref,
        details={
            "tool_output": action_result,
            "fallback_applied": fallback_applied,
            "parameters": proposal.parameters
        }
    )

    return True, action_result, receipt
