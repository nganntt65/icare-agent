"""Pre-filled Email and Walk-in Referral Draft Generator.

Used as:
1. Primary tool for instructor overrides and formal advisory email referrals.
2. Automated fallback recovery when upstream campus booking webhook APIs are down (HTTP 500 / timeout).
"""

from typing import Dict, Any, List
import urllib.parse
import random


def generate_email_draft(
    department: str,
    subject: str,
    recipient_email: str = "",
    student_notes: str = "",
    checklist_items: List[str] = None,
    is_fallback: bool = False
) -> Dict[str, Any]:
    """Generates a complete, pre-filled email draft and walk-in office navigation card.
    
    Args:
        department: Target campus department (e.g. 'Office of International Affairs (OIA)').
        subject: Email subject line.
        recipient_email: Email address (defaults based on department if empty).
        student_notes: Specific inquiry details.
        checklist_items: List of required physical documents to bring.
        is_fallback: Whether this draft was generated due to an upstream API outage.
        
    Returns:
        Structured email draft dictionary with one-click mailto: URL.
    """
    dep_lower = department.lower()
    
    # Resolve default departmental contact information
    if "counsel" in dep_lower or "mental" in dep_lower:
        default_email = "counseling-center@university.edu.tw"
        office_location = "Student Activity Center, 3rd Floor (Room 302)"
        office_hours = "Monday - Friday, 08:30 - 17:30"
        office_phone = "(02) 2362-0000 ext. 2341"
        default_checklist = [
            "Student ID Card",
            "Emergency Contact Information",
            "Health Insurance Card (NHI or Private)"
        ]
    elif "academic" in dep_lower or "override" in dep_lower or "course" in dep_lower:
        default_email = "academic-affairs@university.edu.tw"
        office_location = "Administration Building, 1st Floor (Curriculum Division, Counter 4)"
        office_hours = "Monday - Friday, 08:30 - 17:00"
        office_phone = "(02) 2362-0000 ext. 1102"
        default_checklist = [
            "Course Override Form (加簽單) with Instructor Signature",
            "Student ID Card",
            "Current Semester Course Schedule Printout"
        ]
    else:
        # Default OIA
        default_email = "oia-advising@university.edu.tw"
        office_location = "Administration Building, 2nd Floor (Room 201, International Student Division)"
        office_hours = "Monday - Friday, 09:00 - 17:00 (Counter open 09:30 - 16:30)"
        office_phone = "(02) 2362-0000 ext. 1234"
        default_checklist = [
            "Original Passport and Photocopy",
            "Alien Resident Certificate (ARC) or Entry Visa Stamp",
            "Certificate of Enrollment (在學證明) from Academic Affairs",
            "Two 2-inch Color Photos (white background, taken within 6 months)",
            "NT$ 1,000 Cash Processing Fee"
        ]

    target_email = recipient_email or default_email
    items = checklist_items if checklist_items is not None else default_checklist

    # Build structured email body
    body_lines = [
        f"Dear {department} Advising Team,\n",
        f"I am an international student seeking assistance regarding: {subject}.\n",
        f"Inquiry Details:\n{student_notes or 'I would like to schedule an in-person advising appointment to verify my documentation.'}\n",
        "Required Documents Prepared:\n" + "\n".join(f"- [x] {item}" for item in items),
        "\nThank you for your guidance and support.\n",
        "Sincerely,\nInternational Student\n(Sent via iCare Campus Navigator)"
    ]
    body_text = "\n".join(body_lines)

    # Build mailto: URL
    mailto_params = {
        "subject": subject,
        "body": body_text
    }
    mailto_link = f"mailto:{target_email}?{urllib.parse.urlencode(mailto_params, quote_via=urllib.parse.quote)}"

    draft_num = random.randint(1000, 9999)
    draft_id = f"DRAFT-EML-{draft_num}"

    return {
        "status": "SUCCESS",
        "draft_id": draft_id,
        "department": department,
        "recipient_email": target_email,
        "subject": subject,
        "body": body_text,
        "mailto_url": mailto_link,
        "walk_in_coordinates": {
            "location": office_location,
            "hours": office_hours,
            "phone": office_phone
        },
        "checklist": items,
        "is_fallback": is_fallback,
        "message": (
            f"Pre-filled email draft and walk-in navigation card prepared for {department} ({office_location})."
            if not is_fallback else
            f"⚠️ Upstream booking gateway unavailable. Fallback walk-in card & email draft generated for {office_location}."
        )
    }
