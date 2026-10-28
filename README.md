# SmartDialer — Safe Progressive & Predictive Dialing Prototype

A runnable Python prototype for a collections SmartDialer hiring assignment. It focuses on deterministic safety boundaries, atomic agent allocation, provider abstraction, idempotent event ingestion, conservative recovery, and reproducible simulation.

## Requirements
- Python 3.10+
- No runtime dependencies outside the Python standard library

## Quick start

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m unittest discover -s tests -v
python simulations/run_simulation.py
python simulations/run_load_test.py --agents 1000 --borrowers 5000
```

The load test uses a temporary local SQLite database and mock provider. Results are only a local baseline, not a production throughput guarantee.

## What is implemented
- **Progressive dialing:** one call per currently available agent, with an atomic reservation transaction.
- **Predictive pacing:** a simple explainable estimate based on available agents, answer-rate estimate, average talk time, setup time, and provider health.
- **Safety Controller:** final approval boundary; provider health can stop new requests and approved calls cannot exceed available-agent capacity.
- **State:** explicit agent and call states.
- **Provider adapters:** Provider A is reliable; Provider B simulates periodic failures. Dialer code depends only on the provider interface.
- **Events:** duplicate event IDs are ignored; stale nonterminal events cannot regress a call; terminal states are not overwritten.
- **Recovery:** reserved-but-not-submitted calls are returned to the queue. Ambiguous initiated calls are deliberately not redialed automatically because doing so could duplicate a real-world call.
- **Tests and simulations:** unit tests cover allocation, duplicate/out-of-order events, outage handling, wrap-up, recovery, and provider failures.

## Architecture

```text
Campaign / queued borrowers
          |
          v
 Progressive Dialer OR Predictive Pacing Engine
          |
          v
     Safety Controller  <--- provider health signal
          |
          v
 Atomic Agent + Call Allocator (SQLite transaction)
          |
          v
 TelecomProvider interface
       /          \
 Provider A     Provider B
          |
          v
 Idempotent Provider Event Handler
```

## Important safety and concurrency choices

1. **Atomic allocation:** allocation uses SQLite `BEGIN IMMEDIATE`, then conditionally updates an available agent and queued call in the same transaction. Competing workers serialize at the database write boundary; only one can claim the row.
2. **No predictive bypass:** predictive pacing produces a requested count only. Every request still passes through the Safety Controller.
3. **Conservative dial-ahead:** this prototype only allocates calls to agents that are available now. It intentionally does not place unassigned predictive calls, because an answer without an available agent risks abandonment.
4. **Idempotency:** provider event IDs are stored under a primary key. A repeated ID is ignored. Providers also key mock requests by internal call ID.
5. **Out-of-order events:** lower-rank nonterminal events cannot regress a call. A completion event may arrive without all intermediate events.
6. **Crash recovery:** unsubmitted reservations are safe to requeue. Once a provider request may have been sent, the real system needs a provider idempotency key and reconciliation query before retrying; this prototype avoids blind redial.
7. **Provider outage:** set `dialer.safety.provider_healthy = False` to block new calls. Existing calls remain tracked and should be reconciled from provider events/status queries.

## Predictive pacing model

The current request estimate is:

`ceil((available_agents * setup_seconds / average_talk_seconds) / estimated_answer_rate) * provider_health`

The estimate is clamped to valid input ranges and is **not** the authority to dial. The Safety Controller applies the final capacity limit. For the initial prototype, safe capacity is bounded by currently available agents; this prioritizes correctness over aggressive dial-ahead. Production pacing should use a rolling answer-rate estimate, confidence bounds, abandonment budget, ringing-age distribution, provider latency/failure metrics, and a fast fallback to progressive mode.

## State machines

### Agent
`OFFLINE -> AVAILABLE -> RESERVED -> DIALING -> CONNECTED -> WRAP_UP -> AVAILABLE`

Agents can also be `PAUSED`. Failed setup releases the agent to `AVAILABLE`. In this prototype a terminal provider event moves the agent to `WRAP_UP`; call `finish_wrap_up(agent_id)` after the agent's post-call work is complete.

### Call
`QUEUED -> RESERVED -> INITIATED -> RINGING -> ANSWERED -> CONNECTED -> COMPLETED`

Failure and cancellation can terminate an active call. Provider events can skip intermediate states; stale events are ignored. A production implementation should add event timestamps, provider sequence numbers where available, reconciliation jobs, and a documented transition matrix for every provider's semantics.

## Architecture decision record
See [`docs/architecture_decisions.md`](docs/architecture_decisions.md), plus [`docs/architecture.md`](docs/architecture.md) and [`docs/state_machines.md`](docs/state_machines.md).

## Dataset note
The provided CSV bundle is a synthetic collections analytics dataset with intentionally dirty data. This core dialer prototype does not need to load all 17 tables to demonstrate allocation safety. Keep raw data unchanged; if you extend the simulation with historical answer rates, document cleaning rules and timezone normalization first. Do not commit sensitive or licensed data to a public repository without authorization.

## Limitations / next steps
- SQLite is appropriate for a local prototype, not high-concurrency multi-region production use.
- Provider calls are synchronous mocks; a production system needs durable outbox/inbox patterns and provider reconciliation.
- No real telephone calls are placed.
- The predictive estimate is illustrative; it needs calibration against representative historical data and a defined abandonment threshold.
- Add a lease/heartbeat model and reconciliation for worker crashes after provider submission before enabling automatic retries.
