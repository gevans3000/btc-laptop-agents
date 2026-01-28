# ADR 0003: Broker Protocol Contract

## Status
Proposed

## Context
The system uses multiple broker implementations (`PaperBroker`, `BitunixBroker`, `BacktestBroker`). To ensure maintainability and hot-swappability, we need a strictly defined protocol that all brokers must adhere to.

## Decision
All brokers MUST implement the `BrokerProtocol` defined in `src/laptop_agents/core/protocols.py`.

### Key Requirements:
1. **Idempotency**: Placing the same order (by `client_order_id`) must not result in duplicate positions.
2. **State Transparency**: Brokers must expose `get_position()` and `get_orders()` which return standardized Pydantic models.
3. **Atomic Persistence**: Every state change (fills, cancellations) must be flushed to the primary storage (e.g., SQLite WAL) before returning control to the caller.
4. **Error Handling**: Network failures or exchange rejections must be mapped to standardized system exceptions (`BrokerError`, `InsufficentFundsError`).

## Consequences
- Strategy code remains agnostic of the execution venue.
- Testing is simplified through a single mock implementation of the protocol.
- New exchange integrations only require implementing the standardized methods.
