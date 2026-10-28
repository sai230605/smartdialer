# Architecture

## Components
- **Campaign queue:** queued borrower call records.
- **Dialing strategy:** progressive mode asks for currently available capacity; predictive mode estimates demand from answer-rate and timing inputs.
- **Safety Controller:** the only path from strategy to allocation. It rejects all new requests during provider-health failure and caps approval to safe capacity.
- **Allocator:** uses one SQLite write transaction to reserve both an agent and a call.
- **Provider adapter:** hides provider-specific behaviour behind `TelecomProvider`.
- **Event handler:** deduplicates event IDs and applies monotonic state transitions.
- **Recovery:** requeues reservations that never reached provider submission; does not blindly retry ambiguous provider submissions.

## Why one local process/database first?
The assignment explicitly values a simple design over unnecessary infrastructure. SQLite provides durable state and transactional exclusion for a local prototype. At larger scale, replace it with PostgreSQL conditional updates/row locks, a durable outbox, event inbox deduplication, and worker leases. Keep the Safety Controller logically separate regardless of deployment topology.
