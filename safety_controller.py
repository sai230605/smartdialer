from dataclasses import dataclass

@dataclass(frozen=True)
class SafetyDecision:
    approved: int
    requested: int
    reason: str

class SafetyController:
    """Final non-bypassable dialing limit, independent of pacing strategy."""
    def __init__(self, max_abandon_rate=0.03):
        self.max_abandon_rate = max_abandon_rate
        self.provider_healthy = True

    def approve(self, requested: int, available_agents: int, connected: int,
                ringing: int, reserved: int = 0, progressive: bool = False) -> SafetyDecision:
        requested = max(0, int(requested))
        available_agents = max(0, int(available_agents))
        if not self.provider_healthy:
            return SafetyDecision(0, requested, 'provider unhealthy: pause new calls')
        # Calls that are already initiated/ringing/reserved consume capacity.
        capacity = max(0, available_agents - connected - ringing - reserved)
        if progressive:
            capacity = min(capacity, available_agents)
        approved = min(requested, capacity)
        reason = 'approved' if approved == requested else ('no safe capacity' if approved == 0 else 'reduced to safe capacity')
        return SafetyDecision(approved, requested, reason)
