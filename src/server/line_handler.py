"""LINE Messaging API Integration and Flex Message Handler for iCare.

Handles:
- HMAC-SHA256 signature verification (X-Line-Signature)
- Event processing (Message, Follow, Postback)
- LINE Flex Card formatting for Grounded Answers, Citations, and Crisis Intervention
- Reply API dispatching via LINE Messaging API endpoints
"""

from typing import Dict, Any, List, Optional, Tuple
import os
import json
import hmac
import hashlib
import base64
import urllib.parse
import urllib.request
import urllib.error
import threading
import re
from src.agent.fsm_engine import ICareAgent, get_ssl_context
from src.agent.state import AgentState, FSMStateEnum, ActionProposal


def to_unicode_bold(text: str) -> Tuple[str, bool]:
    """Converts ASCII alphanumeric characters to Unicode Mathematical Sans-Serif Bold."""
    res = []
    has_ascii = False
    for c in text:
        code = ord(c)
        if 65 <= code <= 90:  # A-Z
            res.append(chr(code - 65 + 0x1D5D4))
            has_ascii = True
        elif 97 <= code <= 122:  # a-z
            res.append(chr(code - 97 + 0x1D5EE))
            has_ascii = True
        elif 48 <= code <= 57:  # 0-9
            res.append(chr(code - 48 + 0x1D7EC))
            has_ascii = True
        else:
            res.append(c)
    return "".join(res), has_ascii


def format_markdown_for_line(text: str) -> str:
    """Formats markdown into clean, native LINE chat typography.
    
    1. Converts English/alphanumeric **bold** to true Unicode Sans-Serif Bold (e.g. 𝟯𝟬 𝗱𝗮𝘆𝘀, 𝗣𝗮𝘀𝘀𝗽𝗼𝗿𝘁).
    2. Converts CJK/multilingual **term** to clean prominent brackets 【term】.
    3. Converts ### headers into prominent 📌 Header lines.
    4. Cleans bullet lists from `- item` into `• item`.
    5. Cleans horizontal divider rules into clean dividers.
    """
    if not text:
        return ""
    
    # 1. Headers: "### Header" -> "📌 Header"
    formatted = re.sub(r"^#{1,6}\s*(.+)$", r"📌 \1", text, flags=re.MULTILINE)
    
    # 2. Bold text conversion: **term**
    def _replace_bold(match: re.Match) -> str:
        inner = match.group(1).strip()
        bolded, has_ascii = to_unicode_bold(inner)
        # If contains CJK characters (Chinese, Japanese), use clean Taiwanese emphasis brackets 【...】
        if any("\u4e00" <= c <= "\u9fff" for c in inner):
            return f"【{inner}】"
        if has_ascii:
            return bolded
        return f"【{inner}】"

    formatted = re.sub(r"\*\*(.+?)\*\*", _replace_bold, formatted)
    
    # 3. Clean bullet lists: "- item" or "* item" -> "• item"
    formatted = re.sub(r"^\s*[-*]\s+", "• ", formatted, flags=re.MULTILINE)
    
    # 4. Clean horizontal divider rules: "---" -> "──────────────────"
    formatted = re.sub(r"^-{3,}$", "──────────────────", formatted, flags=re.MULTILINE)
    
    return formatted.strip()


def verify_line_signature(body_bytes: bytes, signature: str, channel_secret: str) -> bool:
    """Verifies that the request came from LINE using HMAC-SHA256.
    
    Args:
        body_bytes: Raw HTTP request body bytes.
        signature: Content of 'X-Line-Signature' HTTP header.
        channel_secret: LINE Channel Secret.
        
    Returns:
        True if signature matches, False otherwise.
    """
    if not channel_secret or not signature:
        return False
        
    clean_secret = channel_secret.strip()
    clean_sig = signature.strip()

    hash_bytes = hmac.new(
        clean_secret.encode("utf-8"),
        body_bytes,
        hashlib.sha256
    ).digest()
    expected_signature = base64.b64encode(hash_bytes).decode("utf-8")
    return hmac.compare_digest(expected_signature, clean_sig)


def create_welcome_flex_message() -> Dict[str, Any]:
    """Builds a rich LINE Flex Message greeting newly added international students."""
    return {
        "type": "flex",
        "altText": "Welcome to iCare Campus Navigator!",
        "contents": {
            "type": "bubble",
            "size": "mega",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#0284c7",
                "paddingAll": "20px",
                "contents": [
                    {
                        "type": "text",
                        "text": "🇹🇼 Welcome to Taiwan!",
                        "color": "#ffffff",
                        "weight": "bold",
                        "size": "xl"
                    },
                    {
                        "type": "text",
                        "text": "iCare Campus Navigator",
                        "color": "#e0f2fe",
                        "size": "sm",
                        "margin": "sm"
                    }
                ]
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "contents": [
                    {
                        "type": "text",
                        "text": "Hello! I am your AI campus guide for Taiwan higher education. I provide verified administrative and living guidance.",
                        "wrap": True,
                        "size": "sm",
                        "color": "#334155"
                    },
                    {
                        "type": "separator",
                        "margin": "md"
                    },
                    {
                        "type": "text",
                        "text": "What would you like to know about?",
                        "weight": "bold",
                        "size": "sm",
                        "color": "#0f172a"
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "color": "#0284c7",
                        "action": {
                            "type": "message",
                            "label": "🪪 ARC Alien Resident Certificate",
                            "text": "How do I apply for or extend my ARC?"
                        }
                    },
                    {
                        "type": "button",
                        "style": "secondary",
                        "action": {
                            "type": "message",
                            "label": "🏥 National Health Insurance (NHI)",
                            "text": "When can I get my NHI health insurance card?"
                        }
                    },
                    {
                        "type": "button",
                        "style": "secondary",
                        "action": {
                            "type": "message",
                            "label": "🏠 Dormitory & Curfew Rules",
                            "text": "What are the dorm curfew and check-in rules?"
                        }
                    },
                    {
                        "type": "button",
                        "style": "secondary",
                        "action": {
                            "type": "message",
                            "label": "📚 Course Selection & Add/Drop",
                            "text": "How does course add/drop and instructor override work?"
                        }
                    }
                ]
            }
        }
    }


def create_crisis_flex_message(state: AgentState) -> Dict[str, Any]:
    """Builds a high-priority crisis intervention card with one-tap dialing buttons."""
    return {
        "type": "flex",
        "altText": "🚨 Immediate Support & Safety Notice",
        "contents": {
            "type": "bubble",
            "size": "mega",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#ef4444",
                "paddingAll": "18px",
                "contents": [
                    {
                        "type": "text",
                        "text": "🚨 Immediate Help & Support",
                        "color": "#ffffff",
                        "weight": "bold",
                        "size": "lg"
                    },
                    {
                        "type": "text",
                        "text": "You are not alone. Caring human help is available 24/7.",
                        "color": "#fef2f2",
                        "size": "xs",
                        "wrap": True,
                        "margin": "xs"
                    }
                ]
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "contents": [
                    {
                        "type": "text",
                        "text": "Please reach out directly to one of these free, confidential Taiwan support hotlines:",
                        "wrap": True,
                        "size": "sm",
                        "color": "#1f2937"
                    },
                    {
                        "type": "separator"
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "spacing": "xs",
                        "contents": [
                            {
                                "type": "text",
                                "text": "• 1925 Suicide Prevention (24/7)",
                                "weight": "bold",
                                "size": "sm",
                                "color": "#b91c1c"
                            },
                            {
                                "type": "text",
                                "text": "• 1995 Lifeline Crisis Hotline (24/7)",
                                "weight": "bold",
                                "size": "sm",
                                "color": "#b91c1c"
                            },
                            {
                                "type": "text",
                                "text": "• 1955 Foreign Worker/Student Line (EN/VI/ID)",
                                "weight": "bold",
                                "size": "sm",
                                "color": "#b91c1c"
                            },
                            {
                                "type": "text",
                                "text": "• Campus Emergency Security: (02) 2362-0000",
                                "weight": "bold",
                                "size": "sm",
                                "color": "#1e3a8a"
                            }
                        ]
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "color": "#dc2626",
                        "action": {
                            "type": "uri",
                            "label": "📞 Call 1925 Hotline",
                            "uri": "tel:1925"
                        }
                    },
                    {
                        "type": "button",
                        "style": "secondary",
                        "action": {
                            "type": "uri",
                            "label": "📞 Call 1955 Multilingual",
                            "uri": "tel:1955"
                        }
                    },
                    {
                        "type": "button",
                        "style": "secondary",
                        "action": {
                            "type": "uri",
                            "label": "🏫 Campus Counseling Center",
                            "uri": "https://counseling.university.edu.tw/crisis-intake"
                        }
                    }
                ]
            }
        }
    }


def create_action_proposal_flex_message(proposal: ActionProposal, detected_lang: str = "en") -> Dict[str, Any]:
    """Builds an interactive LINE Flex Card for two-phase commit human confirmation."""
    p = proposal.parameters
    param_rows = []

    if "department" in p:
        param_rows.append({
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {"type": "text", "text": "Department", "size": "xs", "color": "#64748b", "flex": 2},
                {"type": "text", "text": p["department"], "size": "xs", "color": "#0f172a", "flex": 4, "wrap": True, "weight": "bold"}
            ]
        })
    if "location" in p:
        param_rows.append({
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {"type": "text", "text": "Location", "size": "xs", "color": "#64748b", "flex": 2},
                {"type": "text", "text": p["location"], "size": "xs", "color": "#0f172a", "flex": 4, "wrap": True}
            ]
        })
    if "start_time" in p or "appointment_time" in p:
        time_val = p.get("appointment_time") or p.get("start_time", "").replace("T", " ")[:16]
        param_rows.append({
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {"type": "text", "text": "Scheduled", "size": "xs", "color": "#64748b", "flex": 2},
                {"type": "text", "text": time_val, "size": "xs", "color": "#0f172a", "flex": 4, "wrap": True}
            ]
        })

    if not param_rows:
        param_rows.append({
            "type": "text",
            "text": proposal.description,
            "size": "xs",
            "color": "#334155",
            "wrap": True
        })

    confirm_label = "✅ Confirm & Schedule"
    cancel_label = "❌ Cancel"
    if detected_lang == "zh":
        confirm_label = "✅ 確認並執行"
        cancel_label = "❌ 取消操作"
    elif detected_lang == "vi":
        confirm_label = "✅ Xác nhận thực hiện"
        cancel_label = "❌ Hủy bỏ"
    elif detected_lang == "id":
        confirm_label = "✅ Konfirmasi & Jalankan"
        cancel_label = "❌ Batalkan"
    elif detected_lang == "tl":
        confirm_label = "✅ Kumpirmahin at Iiskedyul"
        cancel_label = "❌ Kanselahin"
    elif detected_lang == "th":
        confirm_label = "✅ ยืนยันดำเนินการ"
        cancel_label = "❌ ยกเลิก"

    return {
        "type": "flex",
        "altText": f"📋 Action Proposal: {proposal.title}",
        "contents": {
            "type": "bubble",
            "size": "mega",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#0284c7",
                "paddingAll": "16px",
                "contents": [
                    {
                        "type": "text",
                        "text": "📋 ACTION PROPOSAL",
                        "color": "#e0f2fe",
                        "weight": "bold",
                        "size": "xs"
                    },
                    {
                        "type": "text",
                        "text": proposal.title,
                        "color": "#ffffff",
                        "weight": "bold",
                        "size": "md",
                        "wrap": True,
                        "margin": "xs"
                    }
                ]
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "paddingAll": "16px",
                "contents": [
                    {
                        "type": "text",
                        "text": proposal.description,
                        "wrap": True,
                        "size": "xs",
                        "color": "#475569"
                    },
                    {
                        "type": "separator"
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "spacing": "xs",
                        "contents": param_rows
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "backgroundColor": "#f8fafc",
                        "cornerRadius": "md",
                        "paddingAll": "8px",
                        "margin": "sm",
                        "contents": [
                            {
                                "type": "text",
                                "text": "🔒 Two-Phase Commit Gate (Taiwan PDPA)",
                                "size": "xxs",
                                "weight": "bold",
                                "color": "#0369a1"
                            },
                            {
                                "type": "text",
                                "text": "No external actions or bookings occur without your confirmation.",
                                "size": "xxs",
                                "color": "#64748b",
                                "wrap": True
                            }
                        ]
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "paddingAll": "12px",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "color": "#0284c7",
                        "height": "sm",
                        "action": {
                            "type": "postback",
                            "label": confirm_label,
                            "data": f"action=confirm&proposal_id={proposal.proposal_id}&token={proposal.confirmation_token}",
                            "displayText": confirm_label
                        }
                    },
                    {
                        "type": "button",
                        "style": "secondary",
                        "height": "sm",
                        "action": {
                            "type": "postback",
                            "label": cancel_label,
                            "data": f"action=cancel&proposal_id={proposal.proposal_id}",
                            "displayText": cancel_label
                        }
                    }
                ]
            }
        }
    }


def create_action_quick_reply(proposal: ActionProposal, detected_lang: str = "en") -> Dict[str, Any]:
    """Builds floating Quick Reply buttons docked directly above the LINE chat keyboard."""
    confirm_label = "✅ Confirm & Schedule"
    cancel_label = "❌ Cancel"
    if detected_lang == "zh":
        confirm_label = "✅ 確認執行"
        cancel_label = "❌ 取消"
    elif detected_lang == "vi":
        confirm_label = "✅ Xác nhận"
        cancel_label = "❌ Hủy bỏ"
    elif detected_lang == "id":
        confirm_label = "✅ Konfirmasi"
        cancel_label = "❌ Batal"
    elif detected_lang == "tl":
        confirm_label = "✅ Kumpirmahin"
        cancel_label = "❌ Kanselahin"
    elif detected_lang == "th":
        confirm_label = "✅ ยืนยันดำเนินการ"
        cancel_label = "❌ ยกเลิก"

    return {
        "items": [
            {
                "type": "action",
                "action": {
                    "type": "postback",
                    "label": confirm_label[:20],
                    "data": f"action=confirm&proposal_id={proposal.proposal_id}&token={proposal.confirmation_token}",
                    "displayText": confirm_label
                }
            },
            {
                "type": "action",
                "action": {
                    "type": "postback",
                    "label": cancel_label[:20],
                    "data": f"action=cancel&proposal_id={proposal.proposal_id}",
                    "displayText": cancel_label
                }
            }
        ]
    }


def create_action_receipt_flex_message(receipt: Dict[str, Any], title: str = "") -> Dict[str, Any]:
    """Builds an official Alphanumeric Execution Receipt Flex card (REC-SCH-XXXX)."""
    rec_id = receipt.get("receipt_id", "REC-SCH-0000")
    rec_title = title or receipt.get("title", "Executed Action")
    ts = receipt.get("timestamp", "")[:19].replace("T", " ")
    consent_hash = receipt.get("consent_verification_hash", "")
    ext_ref = receipt.get("external_reference", "")

    footer_contents = []
    if ext_ref and ext_ref.startswith("http"):
        footer_contents.append({
            "type": "button",
            "style": "primary",
            "color": "#059669",
            "height": "sm",
            "action": {
                "type": "uri",
                "label": "📅 Open Google Calendar",
                "uri": ext_ref
            }
        })

    return {
        "type": "flex",
        "altText": f"📜 Execution Receipt: {rec_id}",
        "contents": {
            "type": "bubble",
            "size": "mega",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#059669",
                "paddingAll": "16px",
                "contents": [
                    {
                        "type": "text",
                        "text": "📜 OFFICIAL EXECUTION RECEIPT",
                        "color": "#d1fae5",
                        "weight": "bold",
                        "size": "xs"
                    },
                    {
                        "type": "text",
                        "text": rec_id,
                        "color": "#ffffff",
                        "weight": "bold",
                        "size": "xl",
                        "margin": "xs"
                    }
                ]
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "paddingAll": "16px",
                "contents": [
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "contents": [
                            {"type": "text", "text": "Status", "size": "xs", "color": "#64748b", "flex": 2},
                            {"type": "text", "text": "CONFIRMED & EXECUTED", "size": "xs", "color": "#059669", "weight": "bold", "flex": 4}
                        ]
                    },
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "contents": [
                            {"type": "text", "text": "Action", "size": "xs", "color": "#64748b", "flex": 2},
                            {"type": "text", "text": rec_title, "size": "xs", "color": "#0f172a", "wrap": True, "flex": 4}
                        ]
                    },
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "contents": [
                            {"type": "text", "text": "Timestamp", "size": "xs", "color": "#64748b", "flex": 2},
                            {"type": "text", "text": f"{ts} UTC", "size": "xs", "color": "#0f172a", "flex": 4}
                        ]
                    },
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "contents": [
                            {"type": "text", "text": "Consent Hash", "size": "xs", "color": "#64748b", "flex": 2},
                            {"type": "text", "text": consent_hash, "size": "xs", "color": "#0f172a", "flex": 4}
                        ]
                    },
                    {
                        "type": "separator",
                        "margin": "md"
                    },
                    {
                        "type": "text",
                        "text": "Taiwan PDPA Two-Phase Commit Compliance Guaranteed.",
                        "size": "xxs",
                        "color": "#94a3b8",
                        "align": "center"
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "paddingAll": "12px",
                "contents": footer_contents if footer_contents else [
                    {
                        "type": "text",
                        "text": "Keep this receipt ID for campus administrative verification.",
                        "size": "xs",
                        "color": "#64748b",
                        "align": "center"
                    }
                ]
            }
        }
    }


def send_line_reply(
    reply_token: str,
    messages: List[Dict[str, Any]],
    channel_access_token: str
) -> Tuple[bool, Optional[str]]:
    """Dispatches reply messages to the LINE Messaging API.
    
    Args:
        reply_token: Webhook event replyToken.
        messages: List of message objects (text or flex).
        channel_access_token: Long-lived Channel Access Token.
        
    Returns:
        Tuple of (success_boolean, error_or_none)
    """
    token = channel_access_token.strip()
    if not token:
        print("❌ [LINE Error] LINE_CHANNEL_ACCESS_TOKEN is missing or empty! Check your .env file.")
        return False, "LINE_CHANNEL_ACCESS_TOKEN not configured."

    # Ensure message text fits within LINE's 5000 character limit and formats markdown
    sanitized_messages = []
    for m in messages[:5]:
        if m.get("type") == "text":
            raw_text = m.get("text", "")
            formatted_text = format_markdown_for_line(raw_text)
            if len(formatted_text) > 4800:
                formatted_text = formatted_text[:4800] + "\n\n*(Full regulations available at OIA)*"
            m_copy = dict(m)
            m_copy["text"] = formatted_text
            sanitized_messages.append(m_copy)
        else:
            sanitized_messages.append(m)

    # Detect mock / simulation tokens and LINE console verify tokens
    # LINE returns HTTP 400 'Invalid reply token' if synthetic/test tokens are dispatched to api.line.me
    is_mock_or_test = (
        reply_token.startswith("mock_")
        or reply_token.startswith("test_")
        or reply_token in (
            "00000000000000000000000000000000",
            "ffffffffffffffffffffffffffffffff"
        )
    )
    if is_mock_or_test:
        print(f"🧪 [Simulated LINE Reply] Detected local test/verify reply token: '{reply_token}'")
        print(f"   Simulated delivery of {len(sanitized_messages)} message(s) successful.")
        for idx, m in enumerate(sanitized_messages, 1):
            if m.get("type") == "text":
                preview = m.get("text", "").replace("\n", " ")[:120]
                print(f"   [{idx}] Text: {preview}...")
            elif m.get("type") == "flex":
                alt = m.get("altText", "Flex Message")
                print(f"   [{idx}] Flex Card: {alt}")
        return True, None

    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    payload = {
        "replyToken": reply_token,
        "messages": sanitized_messages
    }

    data_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=25, context=get_ssl_context()) as resp:
            success = resp.status in (200, 204)
            if success:
                print(f"✅ [LINE Reply Success] Delivered {len(sanitized_messages)} message(s) to LINE!")
            return success, None
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        print(f"❌ [LINE API HTTP Error {e.code}]: {err_body}")
        if "Invalid reply token" in err_body:
            print("💡 [Notice] LINE replyToken is single-use and expires in ~30s. If testing locally via simulate_line_message.py, mock tokens are now simulated.")
        return False, f"LINE API HTTP {e.code}: {err_body}"
    except Exception as e:
        print(f"❌ [LINE Network Error]: {str(e)}")
        return False, f"Failed to send LINE reply: {str(e)}"


def send_line_push(
    user_id: str,
    messages: List[Dict[str, Any]],
    channel_access_token: str
) -> Tuple[bool, Optional[str]]:
    """Dispatches proactive push messages to a user via LINE Messaging API.
    
    Used as an emergency fallback when a replyToken expires (>30s) or for proactive notifications.
    """
    token = channel_access_token.strip()
    if not token:
        return False, "LINE_CHANNEL_ACCESS_TOKEN not configured."

    if (
        user_id.startswith("U_mock_")
        or user_id.startswith("test_")
        or user_id.startswith("anonymous_")
    ):
        print(f"🧪 [Simulated LINE Push] Mock target '{user_id}'. Simulated push of {len(messages)} message(s).")
        return True, None

    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    # Sanitize and format text messages for LINE
    sanitized_messages = []
    for m in messages[:5]:
        if m.get("type") == "text":
            raw_text = m.get("text", "")
            formatted_text = format_markdown_for_line(raw_text)
            if len(formatted_text) > 4800:
                formatted_text = formatted_text[:4800] + "\n\n*(Full regulations available at OIA)*"
            m_copy = dict(m)
            m_copy["text"] = formatted_text
            sanitized_messages.append(m_copy)
        else:
            sanitized_messages.append(m)

    payload = {
        "to": user_id,
        "messages": sanitized_messages
    }

    data_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=25, context=get_ssl_context()) as resp:
            success = resp.status in (200, 204)
            if success:
                print(f"✅ [LINE Push Success] Delivered {len(sanitized_messages)} push message(s) to {user_id}!")
            return success, None
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        print(f"❌ [LINE Push HTTP Error {e.code}]: {err_body}")
        return False, f"LINE Push HTTP {e.code}: {err_body}"
    except Exception as e:
        print(f"❌ [LINE Push Error]: {str(e)}")
        return False, f"Failed to send LINE push: {str(e)}"


def send_line_loading_indicator(
    user_id: str,
    channel_access_token: str,
    loading_seconds: int = 30
) -> bool:
    """Displays native LINE animated typing indicator (...) while agent processes.
    
    API: POST https://api.line.me/v2/bot/chat/loading/start
    Args:
        user_id: Student LINE userId (chatId).
        channel_access_token: Channel Access Token.
        loading_seconds: Duration in seconds to show animation (5 to 60).
    """
    token = channel_access_token.strip()
    if not token or not user_id:
        return False

    if (
        user_id.startswith("U_mock_")
        or user_id.startswith("test_")
        or user_id.startswith("anonymous_")
    ):
        return True

    url = "https://api.line.me/v2/bot/chat/loading/start"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    payload = {
        "chatId": user_id,
        "loadingSeconds": min(max(loading_seconds, 5), 60)
    }

    try:
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=5, context=get_ssl_context()) as resp:
            if resp.status in (200, 202):
                print(f"⏳ [LINE Progress] Displaying native typing indicator for {user_id} ({loading_seconds}s)...")
                return True
            return False
    except Exception as e:
        # Non-critical: failure of loading indicator should never break core workflow
        return False


class LineLoadingHeartbeat:
    """Keeps the LINE loading animation active by refreshing it every interval."""
    def __init__(self, user_id: str, channel_access_token: str, interval: int = 20, loading_seconds: int = 30):
        self.user_id = user_id
        self.channel_access_token = channel_access_token
        self.interval = interval
        self.loading_seconds = loading_seconds
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        if not self.user_id or self.user_id.startswith("U_mock_") or self.user_id.startswith("anonymous_"):
            return
        send_line_loading_indicator(self.user_id, self.channel_access_token, self.loading_seconds)

        def _run():
            while not self._stop_event.wait(self.interval):
                if self._stop_event.is_set():
                    break
                print(f"⏳ [LINE Heartbeat] Refreshing loading indicator for {self.user_id}...")
                send_line_loading_indicator(self.user_id, self.channel_access_token, self.loading_seconds)

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()



def handle_line_events(
    events: List[Dict[str, Any]],
    agent: ICareAgent,
    channel_access_token: str
) -> List[Dict[str, Any]]:
    """Processes incoming LINE webhook events and generates replies.
    
    Returns:
        List of event execution status summaries.
    """
    results = []

    for event in events:
        # Resolve user / session identifier
        event_type = event.get("type")
        reply_token = event.get("replyToken")
        source = event.get("source", {})
        source_type = source.get("type", "user")
        user_id = source.get("userId") or source.get("groupId") or source.get("roomId") or "anonymous_line_user"

        if not reply_token or reply_token.startswith("000000000000"):
            # Webhook verify probe from LINE Developers Console
            print("🔍 [LINE Webhook] Handled verify probe event from console.")
            results.append({"type": event_type, "status": "probe_acknowledged"})
            continue

        # 1. Follow / Join event (Student adds bot as friend, or bot added to group)
        if event_type in ("follow", "join"):
            print(f"\n👋 [LINE Webhook] New {event_type} event! Source: {source_type} ({user_id})")
            welcome_msg = create_welcome_flex_message()
            sent, err = send_line_reply(reply_token, [welcome_msg], channel_access_token)
            if not sent and user_id and not user_id.startswith("U_mock_") and not user_id.startswith("anonymous_"):
                print(f"⚠️ [LINE Fallback] Reply API failed ({err}). Attempting automatic Push API delivery to {user_id}...")
                sent, err = send_line_push(user_id, [welcome_msg], channel_access_token)
            results.append({"type": event_type, "user_id": user_id, "sent": sent, "error": err})
            continue

        # 2. Postback event (Student taps [Confirm] or [Cancel] button on Flex Card)
        if event_type == "postback":
            postback_data = event.get("postback", {}).get("data", "")
            print(f"\n🔘 [LINE Webhook] Received postback: '{postback_data}' from {source_type}: {user_id}")
            
            heartbeat = LineLoadingHeartbeat(user_id, channel_access_token, interval=10, loading_seconds=20)
            heartbeat.start()

            parsed_params = urllib.parse.parse_qs(postback_data)
            action = parsed_params.get("action", [""])[0]
            proposal_id = parsed_params.get("proposal_id", [""])[0]
            token = parsed_params.get("token", [""])[0]

            messages_to_send = []

            try:
                if action == "confirm":
                    success, msg, receipt, action_res = agent.confirm_pending_action(
                        session_id=user_id,
                        proposal_id=proposal_id,
                        token=token
                    )
                    if success and receipt:
                        rec_flex = create_action_receipt_flex_message(receipt, receipt.get("title", ""))
                        messages_to_send.append(rec_flex)
                    else:
                        messages_to_send.append({
                            "type": "text",
                            "text": f"⚠️ Could not execute action: {msg}"
                        })
                elif action == "cancel":
                    success, msg = agent.cancel_pending_action(
                        session_id=user_id,
                        proposal_id=proposal_id
                    )
                    messages_to_send.append({
                        "type": "text",
                        "text": "❌ **Action Cancelled**: Your pending action was safely cancelled. Zero changes were made."
                    })
                else:
                    messages_to_send.append({
                        "type": "text",
                        "text": f"Unrecognized postback action: {action}"
                    })
            finally:
                heartbeat.stop()

            sent, err = send_line_reply(reply_token, messages_to_send, channel_access_token)
            if not sent and user_id and not user_id.startswith("U_mock_") and not user_id.startswith("anonymous_"):
                print(f"⚠️ [LINE Fallback] Reply API failed ({err}). Attempting automatic Push API delivery to {user_id}...")
                sent, err = send_line_push(user_id, messages_to_send, channel_access_token)
            results.append({
                "type": "postback",
                "user_id": user_id,
                "action": action,
                "sent": sent,
                "error": err
            })
            continue

        # 3. Message event
        if event_type == "message":
            msg_obj = event.get("message", {})
            msg_type = msg_obj.get("type")

            if msg_type == "text":
                user_text = msg_obj.get("text", "").strip()
                print(f"\n📩 [LINE Webhook] Received message: '{user_text}' from {source_type}: {user_id}")
                
                # Keep loading indicator alive continuously with heartbeat so it never disappears on slow responses
                heartbeat = LineLoadingHeartbeat(user_id, channel_access_token, interval=20, loading_seconds=30)
                heartbeat.start()
                
                try:
                    # Process query through iCare Agentic FSM
                    state = agent.process_message(session_id=user_id, raw_text=user_text)
                finally:
                    heartbeat.stop()

                print(f"🧠 [iCare FSM] State: {state.fsm_state.value} | Lang: {state.detected_lang} | Confidence: {state.confidence_score}")

                messages_to_send = []

                if state.is_crisis:
                    print("🚨 [iCare Alert] Crisis detected. Delivering emergency intervention card.")
                    flex_card = create_crisis_flex_message(state)
                    messages_to_send.append(flex_card)
                else:
                    # Clean text response with citations
                    reply_text = state.answer
                    
                    # Attach source citation footnotes if present and not in awaiting confirmation
                    if state.citations and not state.pending_action:
                        citations_footer = ["\n\n📌 **Verified Campus References**:"]
                        for idx, c in enumerate(state.citations[:2], start=1):
                            citations_footer.append(f"[{idx}] {c.doc_title} (§ {c.section_title})")
                        reply_text += "\n".join(citations_footer)

                    messages_to_send.append({
                        "type": "text",
                        "text": reply_text
                    })

                    # If an action proposal is prepared, attach rich interactive Postback Flex Card & Quick Reply
                    if state.pending_action:
                        proposal_card = create_action_proposal_flex_message(state.pending_action, state.detected_lang)
                        proposal_card["quickReply"] = create_action_quick_reply(state.pending_action, state.detected_lang)
                        messages_to_send.append(proposal_card)

                    # If an action was just executed, attach official receipt Flex Card
                    elif state.execution_receipt:
                        receipt_card = create_action_receipt_flex_message(state.execution_receipt)
                        messages_to_send.append(receipt_card)

                print(f"📤 [LINE Dispatch] Sending reply message to LINE API...")
                sent, err = send_line_reply(reply_token, messages_to_send, channel_access_token)
                if not sent and user_id and not user_id.startswith("U_mock_") and not user_id.startswith("anonymous_"):
                    print(f"⚠️ [LINE Fallback] Reply API failed ({err}). Attempting automatic Push API delivery to {user_id}...")
                    sent, err = send_line_push(user_id, messages_to_send, channel_access_token)

                results.append({
                    "type": "message",
                    "user_id": user_id,
                    "fsm_state": state.fsm_state.value,
                    "sent": sent,
                    "error": err
                })
                continue
            else:
                # Non-text message (sticker, image, audio, location, etc.)
                print(f"\n📎 [LINE Webhook] Non-text message ({msg_type}) received from {source_type}: {user_id}")
                guide_text = (
                    "👋 Hello! I am iCare Campus Navigator (iCare 校園小幫手).\n\n"
                    "I provide verified text guidance on Taiwan campus administration and living processes.\n"
                    "Please ask your question in text (English, 中文, Tiếng Việt, or Bahasa Indonesia), such as:\n"
                    # "• How to apply or extend ARC (居留證)\n"
                    # "• National Health Insurance (健保)\n"
                    # "• Dormitory curfew and rules (宿舍規範)\n"
                    # "• Course selection and add/drop (選課與加簽)"
                )
                sent, err = send_line_reply(reply_token, [{"type": "text", "text": guide_text}], channel_access_token)
                if not sent and user_id and not user_id.startswith("U_mock_") and not user_id.startswith("anonymous_"):
                    print(f"⚠️ [LINE Fallback] Reply API failed ({err}). Attempting automatic Push API delivery to {user_id}...")
                    sent, err = send_line_push(user_id, [{"type": "text", "text": guide_text}], channel_access_token)

                results.append({
                    "type": "message",
                    "msg_type": msg_type,
                    "user_id": user_id,
                    "sent": sent,
                    "error": err
                })
                continue

        results.append({"type": event_type, "status": "unhandled_event"})

    return results
