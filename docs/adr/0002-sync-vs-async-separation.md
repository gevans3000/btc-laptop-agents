# ADR 002: Sync vs Async Domain Logic

## Status
Accepted

## Context
The system handles high-frequency market data (async) but needs deterministic agent decisions (domain logic). Mixing async code with complex strategy logic often leads to race conditions and "zombie" states.

## Decision
We strictly separate **Async External Shell** (networking, heartbeats, watchdogs) from **Sync Domain Logic** (Supervisor, Agents, Indicators).

## Consequences
- **Determinism**: Replaying a candle through the pipeline is guaranteed to be synchronous and linear.
- **Testability**: Units can be tested without `asyncio` complexity.
- **Reliability**: No `await` calls inside the strategy means we never yield the event loop halfway through a decision.
- **Performance**: Predictable latencies on "laptop-scale" hardware.
- **Bottleneck**: Long-running sync code could block the loop, but since our agents are lightweight (linear complexity), this risk is minimal.
