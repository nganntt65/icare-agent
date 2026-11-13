"""Campus Webhook Intake Dispatcher for OIA and Counseling Center.

Dispatches intake booking requests to campus administrative webhooks with:
- Upstream retry logic (catches 5xx/timeouts and retries twice).
- Configurable live endpoint via CAMPUS_WEBHOOK_URL or sandboxed mock execution.
- Detailed intake ticket generation.
"""

from typing import Dict, Any, Optional
import os
import time
import random
import json
import urllib.request
import urllib.error
from src.agent.fsm_engine import get_ssl_context


class UpstreamWebhookError(Exception):
    """Raised when campus webhook encounters persistent 5xx errors or outages after retries."""
    pass


def dispatch_campus_webhook(
    department: str,
    service_type: str,
    student_id: str = "international_student",
    appointment_time: str = "Next Available Walk-in Slot",
    notes: str = "",
    force_simulate_failure: bool = False
) -> Dict[str, Any]:
    """Dispatches intake booking request to campus systems with 2x retry logic.
    
    Args:
        department: Target department (e.g. 'Office of International Affairs (OIA)', 'Student Counseling Center').
        service_type: Requested service (e.g. 'ARC/Visa Enrollment Verification Intake').
        student_id: Pseudonymized student reference.
        appointment_time: Requested date/time slot.
        notes: Contextual notes or requirements.
        force_simulate_failure: When True, simulates 500 error to test failure recovery.
        
    Returns:
        Structured dispatch confirmation dictionary.
        
    Raises:
        UpstreamWebhookError: If upstream returns 5xx or fails after 2 retries.
    """
    webhook_url = (os.environ.get("CAMPUS_WEBHOOK_URL") or "").strip()
    api_key = (os.environ.get("CAMPUS_API_KEY") or "").strip()
    
    # Check if simulation flag or environment specifies failure simulation
    sim_failure = force_simulate_failure or os.environ.get("CAMPUS_WEBHOOK_SIMULATE_FAIL", "").lower() in ("1", "true", "yes")

    payload = {
        "department": department,
        "service_type": service_type,
        "student_id": student_id,
        "appointment_time": appointment_time,
        "notes": notes,
        "timestamp": time.time()
    }

    max_attempts = 3  # 1 initial + 2 retries
    last_error_msg = ""

    for attempt in range(1, max_attempts + 1):
        try:
            if sim_failure:
                # Simulate upstream 500 server error
                raise urllib.error.HTTPError(
                    url=webhook_url or "https://campus.university.edu.tw/api/intake",
                    code=500,
                    msg="Internal Server Error: Campus Booking Gateway DB Connection Pool Exhausted",
                    hdrs={},
                    fp=None
                )

            if webhook_url and webhook_url.startswith("http"):
                # Live Campus Endpoint POST
                headers = {"Content-Type": "application/json"}
                if api_key:
                    headers["X-Campus-Api-Key"] = api_key

                req = urllib.request.Request(
                    webhook_url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers=headers,
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=5, context=get_ssl_context()) as resp:
                    if resp.status in (200, 201):
                        resp_data = json.loads(resp.read().decode("utf-8"))
                        ticket_id = resp_data.get("ticket_id", f"TICKET-CAMPUS-{random.randint(1000, 9999)}")
                        return {
                            "status": "SUCCESS",
                            "ticket_id": ticket_id,
                            "department": department,
                            "service_type": service_type,
                            "appointment_time": appointment_time,
                            "mode": "LIVE_ENDPOINT",
                            "attempts": attempt,
                            "message": f"Successfully registered intake with {department}. Ticket: {ticket_id}."
                        }
                    else:
                        raise urllib.error.HTTPError(webhook_url, resp.status, "Unexpected status", {}, None)
            else:
                # Sandboxed Mock Dispatch (Always succeeds in standard mode)
                ticket_prefix = "OIA" if "international" in department.lower() or "oia" in department.lower() else "COUNSEL"
                ticket_id = f"TICKET-{ticket_prefix}-{random.randint(1000, 9999)}"
                return {
                    "status": "SUCCESS",
                    "ticket_id": ticket_id,
                    "department": department,
                    "service_type": service_type,
                    "appointment_time": appointment_time,
                    "location": "Administration Building, Room 201" if ticket_prefix == "OIA" else "Student Activity Center, 3F",
                    "mode": "SANDBOX_MOCK",
                    "attempts": attempt,
                    "message": f"Campus intake registered successfully in {department}. Ticket: {ticket_id}."
                }

        except (urllib.error.HTTPError, urllib.error.URLError, Exception) as e:
            last_error_msg = str(e)
            print(f"⚠️ [Campus Webhook Attempt {attempt}/{max_attempts}] Failed: {last_error_msg}")
            if attempt < max_attempts:
                # Exponential backoff jitter
                time.sleep(0.1 * attempt)

    # Exhausted retries -> Raise UpstreamWebhookError to trigger agentic fallback
    raise UpstreamWebhookError(
        f"Campus Webhook failed after {max_attempts} attempts. Upstream error: {last_error_msg}"
    )
