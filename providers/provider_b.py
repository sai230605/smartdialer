from .base import TelecomProvider, ProviderResult

class ProviderB(TelecomProvider):
    """Flaky mock: configurable failures; request IDs remain idempotent."""
    name = 'provider-b'
    def __init__(self, fail_every=4):
        self.fail_every = max(0, int(fail_every))
        self.requests = {}
        self.attempts = 0
    def initiate_call(self, call_id, borrower_id):
        if call_id in self.requests:
            return self.requests[call_id]
        self.attempts += 1
        if self.fail_every and self.attempts % self.fail_every == 0:
            result = ProviderResult(False, error='simulated provider timeout')
        else:
            result = ProviderResult(True, f'b-{call_id}')
        self.requests[call_id] = result
        return result
