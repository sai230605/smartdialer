# State machines

## Agent states
- `OFFLINE`: not logged in / unavailable.
- `AVAILABLE`: eligible for a new call.
- `RESERVED`: atomically claimed for a call.
- `DIALING`: provider accepted call initiation.
- `CONNECTED`: conversation is connected to the agent.
- `WRAP_UP`: call ended; post-call work remains.
- `PAUSED`: agent is temporarily not eligible.

Normal path: `OFFLINE -> AVAILABLE -> RESERVED -> DIALING -> CONNECTED -> WRAP_UP -> AVAILABLE`.

## Call states
- `QUEUED`: waiting for allocation.
- `RESERVED`: an agent has been allocated.
- `INITIATED`: provider accepted initiation.
- `RINGING`: destination is ringing.
- `ANSWERED`: destination answered; agent bridge may still be pending.
- `CONNECTED`: conversation connected to agent.
- `COMPLETED`, `FAILED`, `CANCELLED`: terminal states.

Normal path: `QUEUED -> RESERVED -> INITIATED -> RINGING -> ANSWERED -> CONNECTED -> COMPLETED`.

Provider events can arrive late, duplicated, or without intermediate states. Duplicate event IDs are ignored. A late nonterminal event does not regress a state. Production deployments should model each provider's event semantics and timestamps explicitly.
