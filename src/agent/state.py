"""Typed State Model and FSM Lifecycle Definitions for iCare Agent."""

from typing import List, Dict, Any, Optional
from enum import Enum
from pydantic import BaseModel, Field
from src.retrieval.hybrid_rrf import RankedResult


class FSMStateEnum(str, Enum):
    """Permitted FSM states based on proposal state transition matrix."""
    DISCOVERY = "DISCOVERY"
    SAFETY_EVALUATED = "SAFETY_EVALUATED"
    RESOURCE_MATCHED = "RESOURCE_MATCHED"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    ACTION_EXECUTED = "ACTION_EXECUTED"
    ACTION_FAILED = "ACTION_FAILED"
    CRISIS_ESCALATED = "CRISIS_ESCALATED"
    SECURITY_INTERCEPTED = "SECURITY_INTERCEPTED"
    COMPLETED = "COMPLETED"
    TERMINATED = "TERMINATED"


class ActionType(str, Enum):
    """Permitted action types supported by iCare tool execution layer."""
    GOOGLE_CALENDAR_SYNC = "GOOGLE_CALENDAR_SYNC"
    CAMPUS_WEBHOOK_DISPATCH = "CAMPUS_WEBHOOK_DISPATCH"
    EMAIL_INTAKE_DRAFT = "EMAIL_INTAKE_DRAFT"


class ActionProposal(BaseModel):
    """Structured proposal for an external action requiring explicit human confirmation."""
    proposal_id: str
    action_type: ActionType
    title: str
    description: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    confirmation_token: str
    status: str = "PENDING_CONFIRMATION"  # PENDING_CONFIRMATION, CONFIRMED, CANCELLED, FAILED
    created_at: str = ""


class Citation(BaseModel):
    """Structured citation reference to official institutional policy."""
    source_file: str
    doc_title: str
    section_title: str
    chunk_id: str
    snippet: str
    rrf_score: float


class AgentState(BaseModel):
    """Comprehensive state tracking an interaction turn."""
    session_id: str
    raw_query: str
    sanitized_query: str = ""
    detected_lang: str = "en"
    fsm_state: FSMStateEnum = FSMStateEnum.DISCOVERY
    is_crisis: bool = False
    is_injection: bool = False
    is_purged: bool = False
    redactions: List[Dict[str, str]] = Field(default_factory=list)
    retrieved_results: List[RankedResult] = Field(default_factory=list)
    answer: str = ""
    citations: List[Citation] = Field(default_factory=list)
    confidence_score: float = 0.0
    is_low_confidence: bool = False
    pending_action: Optional[ActionProposal] = None
    execution_receipt: Optional[Dict[str, Any]] = None
    audit_trace: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
