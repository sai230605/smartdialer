# Architecture Decision Record (ADR)

## Status
Accepted for the hiring-assignment prototype.

## Context
The dialer must improve agent utilization while ensuring that a borrower who answers can be handled by an agent. It must also tolerate duplicate/out-of-order events, provider failure, worker crashes, and concurrent workers.

## Decisions
1. **Python + standard library:** minimizes setup friction and makes the prototype easy to run locally.
2. **SQLite:** durable transactional state without requiring a separately managed database. `BEGIN IMMEDIATE` serializes competing writers for this small prototype.
3. **Separate pacing and safety:** pacing can request calls but cannot initiate them. Safety is the final authority and caps calls to currently available agents.
4. **Provider interface + two mocks:** isolates provider-specific behaviour and allows deterministic failure tests.
5. **Event inbox deduplication:** a primary key on provider event ID prevents the same event from being applied twice.
6. **Conservative recovery:** requeue only calls known to be reserved but not yet submitted. Do not automatically retry ambiguous submissions because the provider may already have placed the call.
7. **No real telecom integration:** mock providers keep the assignment reproducible and avoid real-world calling or compliance risk.

## Trade-offs
- SQLite is simple but becomes a write bottleneck for many workers. At scale use PostgreSQL transactions/conditional updates, partitioned queues, and worker leases.
- Conservative pacing sacrifices some utilization to prioritize safety. A production predictor can dial ahead only if it reserves sufficient capacity and enforces a measured abandonment budget.
- Provider mocks do not reproduce all real provider semantics; each adapter needs contract tests and reconciliation logic.

## Scale: 100 -> 1,000 -> 10,000 agents
- **First likely bottleneck:** serialized database writes and repeated queue scans; then event ingestion and provider rate limits.
- **At 1,000 agents:** move to PostgreSQL, add indexes/claim queries, use bounded batches, and measure transaction latency.
- **At 10,000 agents:** partition work by campaign/shard, use leases for workers, durable outbox/inbox processing, backpressure, provider circuit breakers, and independent metrics/alerting. Keep global or partition-level safety capacity accounting strongly consistent.
- **Failure detection:** heartbeats/leases detect worker loss; provider reconciliation resolves ambiguous submissions. Cache is advisory; committed database state is authoritative.

## Final question
I would combine predictive utilization with progressive safety by letting the predictor estimate a target pace but never call the provider directly. A separate Safety Controller would atomically verify available agent capacity, ringing/connected load, provider health, and an abandonment budget before each bounded batch. If answer-rate confidence drops or provider latency rises, it would reduce the batch or fall back to one-call-per-available-agent progressive mode. All reservations and event processing would be idempotent and durable, so prediction can improve efficiency without weakening the safety boundary.
