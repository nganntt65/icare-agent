"""Agent Orchestrator and Finite State Machine (FSM) Engine.

Implements the proposal's State Transition Matrix and FastPathRouter:
- DISCOVERY -> SAFETY_EVALUATED -> RESOURCE_MATCHED -> COMPLETED
- Fast-Path 1: Acute Crisis Interception -> CRISIS_ESCALATED -> TERMINATED
- Fast-Path 2: Prompt-Injection Defense -> SECURITY_INTERCEPTED -> TERMINATED
- Fast-Path 3: Privacy Purge (/forget or /opt_out) -> TERMINATED
- Standard Slow-Path: Cross-lingual normalization, hybrid RRF retrieval,
  grounded synthesis, and citation auditing.
"""

from typing import Dict, Any, Optional, List
import os
import json
import urllib.request
import urllib.error
import ssl
try:
    import certifi
except ImportError:
    certifi = None


def get_ssl_context() -> ssl.SSLContext:
    """Creates an SSL context with certifi CA bundle if available, else default."""
    if certifi:
        try:
            return ssl.create_default_context(cafile=certifi.where())
        except Exception:
            pass
    return ssl.create_default_context()


from src.agent.state import AgentState, FSMStateEnum, Citation, ActionProposal, ActionType
from src.security.crisis_detector import detect_crisis, get_crisis_escalation_payload
from src.security.prompt_injection import detect_prompt_injection, get_injection_blocked_response
from src.security.pii_scrubber import scrub_pii
from src.nlp.language_detector import detect_language
from src.retrieval.hybrid_rrf import HybridRRFRetriever, RankedResult
from src.memory.session_memory import SessionMemoryManager
from src.agent.citation_auditor import CitationAuditor
from src.tools.action_executor import create_action_proposal, execute_action
from src.tools.receipt_emitter import emit_receipt


class ICareAgent:
    """Core Agent Orchestrator managing FSM lifecycles and grounded retrieval."""

    def __init__(self, data_dir: str, confidence_threshold: float = 0.85):
        self.data_dir = data_dir
        self.retriever = HybridRRFRetriever(data_dir=data_dir, rrf_k=60)
        self.memory = SessionMemoryManager(ttl_seconds=1800.0)  # 30-min TTL
        self.auditor = CitationAuditor(confidence_threshold=confidence_threshold)
        
        # Load official campus services directory
        services_path = os.path.join(data_dir, "official_services.json")
        self.official_services = {}
        if os.path.exists(services_path):
            with open(services_path, "r", encoding="utf-8") as f:
                self.official_services = json.load(f)

        # Initialize knowledge index
        self.init_stats = self.retriever.initialize()

    def process_message(self, session_id: str, raw_text: str) -> AgentState:
        """Executes the FSM pipeline for an inbound message."""
        state = AgentState(session_id=session_id, raw_query=raw_text)
        state.audit_trace.append(f"Inbound message received in session {session_id}")

        # -------------------------------------------------------------
        # FAST PATH 0: Pending Action Human-in-the-Loop Confirmation Gate
        # -------------------------------------------------------------
        pending_dict = self.memory.get_pending_action(session_id)
        if pending_dict:
            norm_text = raw_text.strip().lower()
            confirm_keywords = ["confirm", "yes", "proceed", "agree", "ok", "y", "確認", "确认", "đồng ý", "dong y", "setuju", "iya"]
            cancel_keywords = ["cancel", "no", "reject", "stop", "abort", "n", "取消", "hủy", "huy", "batal", "tidak"]

            is_confirm = any(norm_text == kw or norm_text.startswith(kw + " ") for kw in confirm_keywords)
            is_cancel = any(norm_text == kw or norm_text.startswith(kw + " ") for kw in cancel_keywords)

            if is_confirm:
                proposal = ActionProposal(**pending_dict)
                success, action_res, receipt = execute_action(
                    proposal=proposal,
                    confirmation_token=proposal.confirmation_token,
                    session_id=session_id
                )
                self.memory.clear_pending_action(session_id)
                state.fsm_state = FSMStateEnum.ACTION_EXECUTED
                state.execution_receipt = receipt
                state.detected_lang = detect_language(raw_text)

                rec_id = receipt["receipt_id"]
                ts = receipt["timestamp"][:19].replace("T", " ")
                consent_hash = receipt["consent_verification_hash"]
                ext_ref = receipt.get("external_reference", "")

                resp_lines = [
                    "✅ **Action Confirmed & Executed!**\n",
                    f"• **Official Receipt**: `{rec_id}`",
                    f"• **Action**: {proposal.title}",
                    f"• **Timestamp**: {ts} UTC",
                    f"• **Consent Proof**: `{consent_hash}` (Hashed SHA-256)"
                ]
                if ext_ref:
                    if ext_ref.startswith("http"):
                        resp_lines.append(f"• **Access / Calendar Link**: [Open Google Calendar Event]({ext_ref})")
                    else:
                        resp_lines.append(f"• **Reference / Ticket**: `{ext_ref}`")

                if action_res.get("walk_in_coordinates"):
                    coords = action_res["walk_in_coordinates"]
                    resp_lines.append(f"\n📍 **Office Location**: {coords['location']}")
                    resp_lines.append(f"🕒 **Hours**: {coords['hours']}")
                    resp_lines.append(f"📞 **Phone**: {coords['phone']}")

                resp_lines.append("\n*An official immutable execution receipt has been recorded under Taiwan PDPA compliance.*")
                state.answer = "\n".join(resp_lines)
                state.audit_trace.append(f"Action {proposal.proposal_id} confirmed and executed. Receipt: {rec_id}")
                self.memory.record_turn(session_id, "user", raw_text)
                self.memory.record_turn(session_id, "assistant", state.answer)
                return state

            elif is_cancel:
                proposal = ActionProposal(**pending_dict)
                self.memory.clear_pending_action(session_id)
                state.fsm_state = FSMStateEnum.COMPLETED
                state.detected_lang = detect_language(raw_text)
                state.answer = (
                    "❌ **Action Cancelled**: Your request has been safely discarded and session state rolled back. "
                    "Zero external tools or campus endpoints were invoked. You can proceed manually whenever you wish."
                )
                state.audit_trace.append(f"Action {proposal.proposal_id} cancelled by student. State rolled back.")
                self.memory.record_turn(session_id, "user", raw_text)
                self.memory.record_turn(session_id, "assistant", state.answer)
                return state

            else:
                # Mid-conversation goal shift: Clear pending action and proceed with new query
                self.memory.clear_pending_action(session_id)
                state.audit_trace.append("Mid-conversation goal shift: Cleared prior pending action proposal.")

        # -------------------------------------------------------------
        # FAST PATH 3: Privacy Purge Command (/forget, /opt_out)
        # -------------------------------------------------------------
        stripped = raw_text.strip().lower()
        if stripped in ["/forget", "/opt_out", "opt out", "forget me"]:
            self.memory.purge_session(session_id)
            state.fsm_state = FSMStateEnum.TERMINATED
            state.is_purged = True
            state.answer = (
                "🧹 **Session Memory Purged**: Your ephemeral conversation history has been completely deleted "
                "from memory. iCare enforces zero permanent profiling under Taiwan PDPA regulations."
            )
            state.audit_trace.append("Session data purged upon user command")
            return state

        # -------------------------------------------------------------
        # STEP 1: DISCOVERY & SAFETY PRE-FLIGHT
        # -------------------------------------------------------------
        state.fsm_state = FSMStateEnum.DISCOVERY
        state.detected_lang = detect_language(raw_text)
        state.audit_trace.append(f"Detected language: {state.detected_lang}")

        # 1.1 Deterministic Crisis Check (FAST PATH 1)
        is_crisis, crisis_kw = detect_crisis(raw_text)
        if is_crisis:
            state.fsm_state = FSMStateEnum.CRISIS_ESCALATED
            state.is_crisis = True
            crisis_payload = get_crisis_escalation_payload(state.detected_lang)

            lines = [crisis_payload["message"], ""]
            for h in crisis_payload["emergency_hotlines"]:
                lines.append(f"- **{h['name']}**: 📞 **{h['number']}** ({h.get('hours', '24/7')})")
                if "location" in h:
                    lines.append(f"  *Office*: {h['location']}")
            lines.append(f"\n{crisis_payload['next_step']}")

            state.answer = "\n".join(lines)
            state.audit_trace.append(f"Crisis marker intercepted: '{crisis_kw}'. Escalated to hotlines.")
            self.memory.record_turn(session_id, "user", "[CRISIS_INTAKE]")
            self.memory.record_turn(session_id, "assistant", state.answer)
            return state

        # 1.2 Deterministic Prompt Injection Check (FAST PATH 2)
        is_inj, inj_pattern = detect_prompt_injection(raw_text)
        if is_inj:
            state.fsm_state = FSMStateEnum.SECURITY_INTERCEPTED
            state.is_injection = True
            state.answer = get_injection_blocked_response(state.detected_lang)
            state.audit_trace.append(f"Prompt injection intercepted: '{inj_pattern}'. Blocked without LLM call.")
            return state

        # 1.3 PII Regex Scrubbing (Taiwan PDPA Compliance)
        sanitized_text, redactions = scrub_pii(raw_text)
        state.sanitized_query = sanitized_text
        state.redactions = redactions
        if redactions:
            state.audit_trace.append(f"Redacted {len(redactions)} PII item(s) from query before retrieval")

        # Pass safety guardrails -> SAFETY_EVALUATED
        state.fsm_state = FSMStateEnum.SAFETY_EVALUATED
        state.audit_trace.append("Passed all input safety guardrails")

        # -------------------------------------------------------------
        # STEP 2: HYBRID RETRIEVAL (BM25 + Vector RRF)
        # -------------------------------------------------------------
        retrieved_results = self.retriever.search(
            query=state.sanitized_query,
            detected_lang=state.detected_lang,
            top_k=3
        )
        state.retrieved_results = retrieved_results
        state.audit_trace.append(f"Hybrid RRF retrieved {len(retrieved_results)} candidate chunks")

        # -------------------------------------------------------------
        # STEP 3: GROUNDED SYNTHESIS (RESOURCE_MATCHED)
        # -------------------------------------------------------------
        state.fsm_state = FSMStateEnum.RESOURCE_MATCHED
        raw_answer = self._synthesize_grounded_answer(
            query=state.sanitized_query,
            retrieved_chunks=retrieved_results,
            language=state.detected_lang
        )

        # -------------------------------------------------------------
        # STEP 4: FAITHFULNESS & CITATION AUDIT
        # -------------------------------------------------------------
        audited_answer, citations, confidence, is_low_conf = self.auditor.audit_and_format(
            answer=raw_answer,
            retrieved_results=retrieved_results,
            language=state.detected_lang
        )

        state.citations = citations
        state.confidence_score = confidence
        state.is_low_confidence = is_low_conf
        state.audit_trace.append(f"Audited citations attached. Confidence score: {confidence}")

        # -------------------------------------------------------------
        # STEP 5: ACTION PROPOSAL EVALUATION (Two-Phase Commit Gate)
        # -------------------------------------------------------------
        action_proposal = self._detect_actionable_proposal(
            query=state.sanitized_query,
            retrieved_chunks=retrieved_results,
            language=state.detected_lang
        )

        if action_proposal:
            self.memory.set_pending_action(session_id, action_proposal.model_dump())
            state.pending_action = action_proposal
            state.fsm_state = FSMStateEnum.AWAITING_CONFIRMATION

            proposal_note = self._format_proposal_callout(action_proposal, state.detected_lang)
            state.answer = audited_answer + proposal_note
            state.audit_trace.append(
                f"Action proposal prepared: {action_proposal.proposal_id} ({action_proposal.action_type.value}). "
                "Awaiting explicit user confirmation."
            )
        else:
            state.answer = audited_answer
            state.fsm_state = FSMStateEnum.COMPLETED

        # Record turns in ephemeral session memory
        self.memory.record_turn(session_id, "user", state.sanitized_query)
        self.memory.record_turn(session_id, "assistant", state.answer)

        return state

    def confirm_pending_action(
        self,
        session_id: str,
        proposal_id: str,
        token: str
    ) -> Tuple[bool, str, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """Confirms and executes a pending action via LINE Postback or REST API."""
        pending = self.memory.get_pending_action(session_id)
        if not pending:
            return False, "No active pending action found for this session.", None, None

        proposal = ActionProposal(**pending)
        if proposal.proposal_id != proposal_id:
            return False, f"Proposal ID mismatch: expected {proposal.proposal_id}, got {proposal_id}.", None, None

        try:
            success, action_res, receipt = execute_action(proposal, token, session_id)
            self.memory.clear_pending_action(session_id)
            return True, "Action successfully confirmed and executed.", receipt, action_res
        except PermissionError as pe:
            return False, str(pe), None, None
        except Exception as e:
            return False, f"Action execution failed: {str(e)}", None, None

    def cancel_pending_action(
        self,
        session_id: str,
        proposal_id: str
    ) -> Tuple[bool, str]:
        """Safely cancels a pending action proposal with zero external mutations."""
        pending = self.memory.get_pending_action(session_id)
        if not pending:
            return False, "No active pending action found for this session."

        self.memory.clear_pending_action(session_id)
        return True, "Action proposal successfully cancelled and state rolled back."

    def _detect_actionable_proposal(
        self,
        query: str,
        retrieved_chunks: List[RankedResult],
        language: str
    ) -> Optional[ActionProposal]:
        """Detects whether a query warrants an actionable proposal requiring human confirmation."""
        q_lower = query.lower()

        # 1. Google Calendar Sync: ARC expiry / Health Exam / Explicit calendar request
        is_calendar_explicit = any(k in q_lower for k in [
            "calendar", "google calendar", "schedule reminder", "add to calendar", "lịch", "jadwal", "行事曆", "提醒",
            "kalendaryo", "paalala", "ปฏิทิน", "แจ้งเตือน"
        ])
        is_arc_expiry = ("arc" in q_lower or "thẻ cư trú" in q_lower or "kartu izin" in q_lower or "居留證" in q_lower or "permit" in q_lower or "pananatili" in q_lower or "บัตร arc" in q_lower or "บัตรถิ่นที่อยู่" in q_lower) and any(
            k in q_lower for k in [
                "expire", "three days", "3 days", "hết hạn", "habis", "到期", "deadline", "renew", "gia hạn", "perpanjang",
                "mag-expire", "mag-renew", "mapapaso", "i-renew", "หมดอายุ", "ต่ออายุ"
            ]
        )
        is_health_exam = ("health exam" in q_lower or "form b" in q_lower or "khám sức khỏe" in q_lower or "體檢" in q_lower or "eksaminasyong medikal" in q_lower or "pagsusuring pangkalusugan" in q_lower or "ตรวจสุขภาพ" in q_lower or "แบบฟอร์มบี" in q_lower) and any(
            k in q_lower for k in [
                "deadline", "submit", "nộp", "kumpul", "繳交", "when", "khi nào", "kapan",
                "kailan", "ipasa", "เมื่อไหร่", "ส่ง"
            ]
        )

        if is_arc_expiry or (is_calendar_explicit and ("arc" in q_lower or "居留證" in q_lower or "บัตร" in q_lower or "permit" in q_lower)):
            return create_action_proposal(
                action_type=ActionType.GOOGLE_CALENDAR_SYNC,
                title="Add ARC Renewal Window to Google Calendar",
                description="Synchronize NIA Alien Resident Certificate extension window deadline with calendar.",
                parameters={
                    "title": "NIA ARC Extension Window Deadline",
                    "start_time": "2026-10-15T09:00:00+08:00",
                    "end_time": "2026-10-15T11:00:00+08:00",
                    "location": "National Immigration Agency (NIA) Service Center, Taipei (No. 15, Guangzhou St)",
                    "description": "Submit ARC renewal: Bring Passport, Student ID/Certificate of Enrollment (在學證明), 2-inch photo, and NT$1,000 fee."
                }
            )

        if is_health_exam or (is_calendar_explicit and ("exam" in q_lower or "體檢" in q_lower or "medikal" in q_lower or "สุขภาพ" in q_lower)):
            return create_action_proposal(
                action_type=ActionType.GOOGLE_CALENDAR_SYNC,
                title="Add Health Exam (Form B) Submission Deadline to Google Calendar",
                description="Synchronize mandatory Form B health examination report submission deadline.",
                parameters={
                    "title": "Campus Health Exam (Form B) Submission Deadline",
                    "start_time": "2026-10-20T14:00:00+08:00",
                    "end_time": "2026-10-20T16:00:00+08:00",
                    "location": "Campus Health Center, 1st Floor",
                    "description": "Submit completed Form B health exam report from designated Taiwan hospital to Health Center."
                }
            )

        # 2. Campus Webhook Dispatch: OIA In-Person Booking / Webhook test / Counseling
        is_webhook_explicit = "webhook" in q_lower
        is_oia_booking = any(k in q_lower for k in [
            "book", "appointment", "schedule", "đặt lịch", "janji temu", "預約", "臨櫃",
            "mag-book", "iskedyul", "จอง", "นัดหมาย", "เวลานัด"
        ]) and any(
            k in q_lower for k in [
                "oia", "advisor", "room 201", "international office", "phòng 201", "國際處",
                "opisina ng ugnayang pandaigdig", "สำนักงานวิเทศสัมพันธ์", "ห้อง 201"
            ]
        )
        is_counseling_booking = any(k in q_lower for k in [
            "counseling", "counselor", "tư vấn tâm lý", "konseling", "心理諮商", "諮商",
            "pagpapayo", "konsultasyon sa pag-iisip", "ปรึกษาจิตวิทยา", "ให้คำปรึกษา"
        ]) and any(
            k in q_lower for k in ["book", "appointment", "intake", "đặt lịch", "janji", "預約", "mag-book", "จอง", "นัดหมาย"]
        )

        if is_webhook_explicit or is_oia_booking:
            return create_action_proposal(
                action_type=ActionType.CAMPUS_WEBHOOK_DISPATCH,
                title="Schedule OIA In-Person Advising Intake via Campus Webhook",
                description="Dispatches intake request to campus scheduling webhook for Admin Building Room 201 advising.",
                parameters={
                    "department": "Office of International Affairs (OIA)",
                    "service_type": "International Student Administrative & Visa Intake",
                    "appointment_time": "Walk-in Slot (Mon-Fri 09:30 - 16:30)",
                    "location": "Administration Building, Room 201",
                    "notes": f"Inquiry context: {query[:120]}"
                }
            )

        if is_counseling_booking:
            return create_action_proposal(
                action_type=ActionType.CAMPUS_WEBHOOK_DISPATCH,
                title="Schedule Campus Counseling Center Intake via Campus Webhook",
                description="Dispatches initial counseling intake request to Student Counseling Center webhook.",
                parameters={
                    "department": "Student Counseling Center",
                    "service_type": "Cross-Cultural Adjustment Counseling Intake",
                    "appointment_time": "Next Available Slot (Mon-Fri 08:30 - 17:30)",
                    "location": "Student Activity Center, 3F",
                    "notes": f"Intake context: {query[:120]}"
                }
            )

        # 3. Email Intake Draft: Course override (加簽) or formal professor/advisor draft
        is_override = any(k in q_lower for k in [
            "override", "加簽", "jiaqian", "xin chữ ký", "tanda tangan",
            "lagda ng propesor", "pahintulot sa kurso", "เซ็นเพิ่มวิชา", "ลงทะเบียนเพิ่มพิเศษ"
        ]) or (
            ("course" in q_lower or "class" in q_lower or "選課" in q_lower or "môn học" in q_lower or "kurso" in q_lower or "วิชา" in q_lower) and 
            any(k in q_lower for k in ["full", "add/drop", "instructor", "hết chỗ", "penuh", "滿了", "email", "mail", "puno", "เต็ม"])
        )

        if is_override:
            return create_action_proposal(
                action_type=ActionType.EMAIL_INTAKE_DRAFT,
                title="Draft Course Override Instructor Email (加簽申請信)",
                description="Generates pre-filled instructor email draft with course code, student details, and Curriculum Division workflow.",
                parameters={
                    "department": "Curriculum Division & Course Instructor",
                    "subject": "[iCare] International Student Course Override Request (加簽申請)",
                    "notes": f"Student request: {query[:120]}"
                }
            )

        return None

    def _format_proposal_callout(self, proposal: ActionProposal, language: str) -> str:
        """Formats the bilingual proposal action callout card for chat display."""
        param_items = []
        p = proposal.parameters
        if "location" in p:
            param_items.append(f"Location: {p['location']}")
        if "start_time" in p:
            param_items.append(f"Time: {p['start_time'][:16].replace('T', ' ')}")
        if "department" in p:
            param_items.append(f"Department: {p['department']}")
        param_str = "; ".join(param_items) if param_items else proposal.description

        if language == "zh":
            return (
                "\n\n---\n"
                "📋 **【待授權執行項目】（人機協同雙階段確認）**\n"
                f"• **動作項目**：{proposal.title}\n"
                f"• **預設參數**：{param_str}\n"
                "🔒 *安全把關（台灣個資法規範）*：在您明確授權確認前，系統絕不會向外部 API 發送請求或更動任何紀錄。\n\n"
                "👉 **確認執行**：請點擊下方 **[✅ 確認執行]** 或直接回覆 **「確認」**\n"
                "👉 **取消操作**：請點擊 **[❌ 取消]** 或直接回覆 **「取消」**"
            )
        elif language == "vi":
            return (
                "\n\n---\n"
                "📋 **【Đề Xuất Hành Động Chờ Xác Nhận】**\n"
                f"• **Hành động**: {proposal.title}\n"
                f"• **Thông số**: {param_str}\n"
                "🔒 *Bảo vệ an toàn*: iCare không tự ý kích hoạt API ngoài khi chưa có sự đồng ý của bạn.\n\n"
                "👉 **Xác nhận**: Nhấn nút **[✅ Xác nhận]** hoặc nhắn **'confirm'**\n"
                "👉 **Hủy bỏ**: Nhấn nút **[❌ Hủy]** hoặc nhắn **'cancel'**"
            )
        elif language == "id":
            return (
                "\n\n---\n"
                "📋 **【Usulan Tindakan Menunggu Konfirmasi】**\n"
                f"• **Tindakan**: {proposal.title}\n"
                f"• **Parameter**: {param_str}\n"
                "🔒 *Perlindungan Privasi*: iCare tidak akan memicu API eksternal tanpa izin eksplisit Anda.\n\n"
                f"👉 **Konfirmasi**: Klik **[✅ Konfirmasi]** atau balas **'confirm'**\n"
                f"👉 **Batalkan**: Klik **[❌ Batal]** atau balas **'cancel'**"
            )
        elif language == "tl":
            return (
                "\n\n---\n"
                "📋 **【Mungkahing Aksyon na Naghihintay ng Pagkumpirma】**\n"
                f"• **Aksyon**: {proposal.title}\n"
                f"• **Mga Detalye**: {param_str}\n"
                "🔒 *Proteksyon sa Privacy (Taiwan PDPA)*: Hindi magti-trigger ang iCare ng panlabas na API nang walang tahasang pahintulot.\n\n"
                "👉 **Upang Isagawa**: I-click ang **[✅ Kumpirmahin]** o mag-reply ng **\"confirm\"**\n"
                "👉 **Upang Kanselahin**: I-click ang **[❌ Kanselahin]** o mag-reply ng **\"cancel\"**"
            )
        elif language == "th":
            return (
                "\n\n---\n"
                "📋 **【ข้อเสนอการดำเนินการ รอการยืนยันจากคุณ】**\n"
                f"• **การดำเนินการ**: {proposal.title}\n"
                f"• **รายละเอียด**: {param_str}\n"
                "🔒 *การคุ้มครองความเป็นส่วนตัว (Taiwan PDPA)*: iCare จะไม่เรียกใช้ API ภายนอกหรือบันทึกข้อมูลใดๆ หากไม่ได้รับความยินยอมจากคุณ\n\n"
                "👉 **ยืนยันดำเนินการ**: คลิก **[✅ ยืนยันดำเนินการ]** หรือพิมพ์ตอบกลับ **\"confirm\"**\n"
                "👉 **ยกเลิก**: คลิก **[❌ ยกเลิก]** หรือพิมพ์ตอบกลับ **\"cancel\"**"
            )
        else:
            return (
                "\n\n---\n"
                "📋 **【Action Proposal Awaiting Your Confirmation】**\n"
                f"• **Action**: {proposal.title}\n"
                f"• **Details**: {param_str}\n"
                "🔒 *Two-Phase Commit Gate (Taiwan PDPA)*: iCare will NOT trigger external APIs or bookings without your explicit confirmation.\n\n"
                "👉 **To Execute**: Click **[✅ Confirm & Schedule]** or reply **\"confirm\"**\n"
                "👉 **To Discard**: Click **[❌ Cancel]** or reply **\"cancel\"**"
            )

    def _call_gemini_flash_api(
        self,
        api_key: str,
        system_instruction: str,
        user_prompt: str
    ) -> Optional[str]:
        """Calls the Gemini Flash REST API directly without third-party dependencies."""
        # Allow environment override, otherwise default to current recommended models with fast fallback
        custom_model = (os.environ.get("GEMINI_MODEL") or "").strip()
        models_to_try = [custom_model] if custom_model else [
            "gemini-3.5-flash",
            "gemini-3.8-flash",
            "gemini-flash-latest",
            "gemini-flash-lite-latest"
        ]
        
        ssl_ctx = get_ssl_context()
        for model_name in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key.strip()}"
            headers = {"Content-Type": "application/json"}

            # Ample token limit (3072) prevents MAX_TOKENS mid-sentence truncation.
            # Fast thinking budget (0) bypasses hidden reasoning tokens to deliver instant ~2s responses.
            gen_config = {
                "temperature": 0.0,
                "maxOutputTokens": 3072
            }
            if "lite" not in model_name:
                gen_config["thinkingConfig"] = {"thinkingBudget": 0}

            payload = {
                "system_instruction": {
                    "parts": [{"text": system_instruction}]
                },
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": user_prompt}]
                    }
                ],
                "generationConfig": gen_config
            }

            try:
                data_bytes = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=15, context=ssl_ctx) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    candidates = resp_data.get("candidates", [])
                    if candidates:
                        cand = candidates[0]
                        finish_reason = cand.get("finishReason")
                        if finish_reason == "MAX_TOKENS":
                            print(f"⚠️ [Gemini API] Response reached MAX_TOKENS ceiling with model {model_name}")
                        parts = cand.get("content", {}).get("parts", [])
                        text_parts = [p.get("text", "") for p in parts if isinstance(p, dict) and "text" in p]
                        if text_parts:
                            return "".join(text_parts).strip()
            except urllib.error.HTTPError as e:
                err_text = e.read().decode("utf-8")
                # If thinkingConfig was not supported (HTTP 400), retry without it
                if e.code == 400 and "thinkingConfig" in gen_config:
                    try:
                        del gen_config["thinkingConfig"]
                        data_bytes = json.dumps(payload).encode("utf-8")
                        req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
                        with urllib.request.urlopen(req, timeout=15, context=ssl_ctx) as retry_resp:
                            resp_data = json.loads(retry_resp.read().decode("utf-8"))
                            candidates = resp_data.get("candidates", [])
                            if candidates:
                                parts = candidates[0].get("content", {}).get("parts", [])
                                text_parts = [p.get("text", "") for p in parts if isinstance(p, dict) and "text" in p]
                                if text_parts:
                                    return "".join(text_parts).strip()
                    except Exception:
                        pass
                print(f"⚠️ [Gemini API] HTTP Error {e.code} with model {model_name}: {err_text[:200]}")
            except Exception as e:
                print(f"⚠️ [Gemini API] Network Error with model {model_name}: {str(e)}")

        return None

    def _synthesize_grounded_answer(
        self,
        query: str,
        retrieved_chunks: List[RankedResult],
        language: str
    ) -> str:
        """Synthesizes a helpful, grounded response from verified institutional chunks.
        
        If GEMINI_API_KEY is available, invokes Gemini Flash LLM via REST API;
        otherwise, performs structured offline grounded synthesis.
        """
        gemini_key = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()
        if gemini_key:
            print(f"✨ [iCare LLM] Invoking Gemini Flash with {len(retrieved_chunks)} grounded knowledge chunks...")
            context_str = "\n\n---\n\n".join(
                f"[{c.doc_title} - {c.section_title}]\n{c.content}" for c in retrieved_chunks
            )
            lang_names = {
                "en": "English",
                "vi": "Vietnamese (Tiếng Việt)",
                "id": "Indonesian (Bahasa Indonesia)",
                "zh": "Traditional Chinese (繁體中文)",
                "tl": "Filipino / Tagalog",
                "th": "Thai (ภาษาไทย)"
            }
            target_lang = lang_names.get(language, "English")

            system_instruction = (
                "You are iCare, an empathetic, culturally supportive campus administrative assistant "
                "for international students studying in Taiwan.\n"
                "CRITICAL INSTRUCTIONS:\n"
                f"1. Respond directly and naturally in {target_lang}.\n"
                "2. Base your answer STRICTLY on the official campus documentation provided below.\n"
                "3. Provide clear step-by-step guidance, exact fee amounts, locations, and deadlines.\n"
                "4. Structure your response with concise bullet points and bold section headers. Avoid unnecessary conversational filler.\n"
                "5. Ensure your response is complete and does not cut off mid-sentence.\n"
                "6. Do NOT make up information or diagnose medical conditions."
            )
            user_prompt = f"Official Campus Documentation:\n{context_str}\n\nStudent Inquiry: {query}"
            
            llm_response = self._call_gemini_flash_api(gemini_key, system_instruction, user_prompt)
            if llm_response:
                print(f"✅ [iCare LLM] Gemini Flash successfully generated natural grounded response ({len(llm_response)} chars).")
                return llm_response
            else:
                print("⚠️ [iCare LLM] Gemini API call returned None; falling back to grounded extraction.")
        else:
            print("ℹ️ [iCare Synthesis] GEMINI_API_KEY not configured in .env; using offline extraction fallback.")

        # Deterministic Offline Synthesis Engine (100% grounded in verified source docs)
        if not retrieved_chunks:
            no_info_messages = {
                "en": "I could not find official university documentation directly matching your inquiry.",
                "zh": "目前在官方校園知識庫中未檢索到與您提問直接相符的章程。",
                "vi": "Tôi không tìm thấy văn bản quy định chính thức nào của trường khớp với câu hỏi của bạn.",
                "id": "Saya tidak menemukan dokumentasi resmi kampus yang cocok dengan pertanyaan Anda.",
                "tl": "Wala akong nahanap na opisyal na dokumentasyon ng unibersidad na tumutugma sa iyong katanungan.",
                "th": "ไม่พบเอกสารระเบียบการอย่างเป็นทางการของมหาวิทยาลัยที่ตรงกับคำถามของคุณในขณะนี้"
            }
            return no_info_messages.get(language, no_info_messages["en"])

        top = retrieved_chunks[0]
        
        # Build structured response with primary finding and action checklist
        header_messages = {
            "en": f"### Verified Information: {top.doc_title}\n*Topic: {top.section_title}*",
            "zh": f"### 官方核實資訊：{top.doc_title}\n*主題：{top.section_title}*",
            "vi": f"### Thông Tin Đã Xác Thực: {top.doc_title}\n*Chủ đề: {top.section_title}*",
            "id": f"### Informasi Terverifikasi: {top.doc_title}\n*Topik: {top.section_title}*",
            "tl": f"### Na-verify na Impormasyon: {top.doc_title}\n*Paksa: {top.section_title}*",
            "th": f"### ข้อมูลที่ผ่านการตรวจสอบอย่างเป็นทางการ: {top.doc_title}\n*หัวข้อ: {top.section_title}*"
        }

        header = header_messages.get(language, header_messages["en"])
        
        # Format the core verified content cleanly
        body_lines = [header, ""]
        body_lines.append(top.content)

        # If supplementary chunks exist (e.g. specific fee or office location)
        for sec in retrieved_chunks[1:3]:
            if sec.section_title != top.section_title:
                sec_headers = {
                    "en": f"\n#### Specific Regulations: {sec.section_title}",
                    "zh": f"\n#### 詳細規範：{sec.section_title}",
                    "vi": f"\n#### Quy định chi tiết: {sec.section_title}",
                    "id": f"\n#### Regulasi Terkait: {sec.section_title}",
                    "tl": f"\n#### Mga Detalyadong Regulasyon: {sec.section_title}",
                    "th": f"\n#### ระเบียบข้อบังคับที่เกี่ยวข้อง: {sec.section_title}"
                }
                body_lines.append(sec_headers.get(language, sec_headers["en"]))
                body_lines.append(sec.content)

        return "\n".join(body_lines)
