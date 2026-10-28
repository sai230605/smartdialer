from .base import TelecomProvider, ProviderResult

class ProviderA(TelecomProvider):
    """Fast/reliable deterministic mock provider."""
    name = 'provider-a'
    def __init__(self):
        self.requests = {}
    def initiate_call(self, call_id, borrower_id):
        provider_id = self.requests.setdefault(call_id, f'a-{call_id}')
        return ProviderResult(True, provider_id)
