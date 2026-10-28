from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class ProviderResult:
    accepted: bool
    provider_call_id: str | None = None
    error: str | None = None

class TelecomProvider(ABC):
    name = 'base'
    @abstractmethod
    def initiate_call(self, call_id: str, borrower_id: str) -> ProviderResult:
        """Submit a call request. Implementations must be idempotent by call_id."""
