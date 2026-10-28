from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

class AgentState(str, Enum):
    OFFLINE = "OFFLINE"
    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"
    DIALING = "DIALING"
    CONNECTED = "CONNECTED"
    WRAP_UP = "WRAP_UP"
    PAUSED = "PAUSED"

class CallState(str, Enum):
    QUEUED = "QUEUED"
    RESERVED = "RESERVED"
    INITIATED = "INITIATED"
    RINGING = "RINGING"
    ANSWERED = "ANSWERED"
    CONNECTED = "CONNECTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

TERMINAL_CALL_STATES = {CallState.COMPLETED, CallState.FAILED, CallState.CANCELLED}

@dataclass
class Agent:
    id: str
    state: AgentState = AgentState.AVAILABLE
    current_call_id: Optional[str] = None

@dataclass
class Call:
    id: str
    borrower_id: str
    state: CallState = CallState.QUEUED
    agent_id: Optional[str] = None
    provider_call_id: Optional[str] = None
    version: int = 0
    processed_events: set[str] = field(default_factory=set)
    failure_reason: Optional[str] = None

@dataclass(frozen=True)
class ProviderEvent:
    event_id: str
    call_id: str
    event_type: str
    provider_call_id: Optional[str] = None
