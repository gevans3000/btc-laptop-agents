# Test Strategy & Execution Plan: BTC Laptop Agents
**Version**: 1.0.0
**Status**: DRAFT
**Role**: Senior QA Lead / Test Engineer

---

## 1. Test Plan Overview

### A. Scope
**In Scope:**
- **Trading Engine Core**: Signal generation, risk management, order execution logic.
- **Broker Adapters**: Bitunix (Real) and PaperBroker (Simulated).
- **CLI Interface**: `la` commands (`start`, `stop`, `run`, `doctor`, `watch`, `status`).
- **Data Providers**: WebSocket feeds, REST fallback, Mock data.
- **Resilience Layer**: Checkpointing, crash recovery, watchdog process.
- **Dashboard UI**: Flask-based monitoring dashboard and generated HTML reports.
- **Safety Gates**: Kill switch, daily loss limits, funding rate gates.

**Out of Scope:**
- Third-party exchange infrastructure stability (Bitunix side).
- OS-level network stack failures (beyond basic detection).
- Hardware failure recovery (e.g., laptop battery death).

### B. Test Objectives & Quality Criteria ("What is Perfect?")
1. **Zero Financial Leakage**: No trade should exceed the risk limits defined in configuration.
2. **Determinism**: Given the same input data, the engine must produce identical signals and trade executions.
3. **Resilience**: The system must recover state within 30 seconds of a process crash.
4. **Data Integrity**: All trades must be logged to CSV/JSON without corruption, even during shutdown.
5. **Observability**: Dashboard must reflect actual system state with < 5s latency.

### C. Risks, Assumptions, and Dependencies
- **Risk**: API Rate limiting from Bitunix during high-frequency testing.
- **Assumption**: Testing will use a dedicated Bitunix sub-account or Paper trading for destructive tests.
- **Dependency**: Connectivity to Bitunix API for integration/E2E stages.

---

## 2. Test Matrix

| Module | Unit | Integration | E2E | Smoke | Regression | Priority | Rationale |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- | :--- |
| **Risk Sentinel** | X | X | X | X | X | P0 | Prevents financial loss. |
| **Bitunix Broker** | X | X | X | X | X | P0 | Controls real funds. |
| **Setup Signals** | X | X | | | X | P1 | Core profitability logic. |
| **Checkpointing** | | X | X | | X | P1 | Ensures session survival. |
| **Dashboard UI** | | | X | X | | P2 | Operational monitoring. |
| **CLI (la)** | | | X | X | | P1 | Primary user interface. |
| **Log Scrubbing** | X | | | | | P2 | Privacy/Security. |

---

## 3. Detailed Test Cases

### Group 1: Happy Paths (Core Flow)
| ID | Title | Preconditions | Steps | Expected Result |
| :--- | :--- | :--- | :--- | :--- |
| TC-01 | Successful Long Entry | Mode: Live-Session. Strategy: Default. | 1. Start agent. 2. Feed long signal data. | Order placed on Bitunix/Paper as Market. |
| TC-02 | Take Profit Execution | Position open. Price hits TP. | 1. Monitor price. 2. Observe TP hit. | Limit sell order executed, position closed. |
| TC-03 | Stop Loss Execution | Position open. Price hits SL. | 1. Monitor price. 2. Observe SL hit. | Market sell executed immediately. |
| TC-04 | CLI `la doctor` | Env configured. | 1. Run `la doctor`. | Returns [OK] for all checks. |
| TC-05 | Dashboard Update | Session running. | 1. Open Browser to Dash. 2. Place Trade. | Trade appears in "Recent Events" within 5s. |
| TC-06 | Multi-Asset Watch | `la run --symbol BTC,ETH` | 1. Start session. | Two independent streams running. |
| TC-07 | Report Generation | Session ended. | 1. Stop session. 2. Check `.workspace/runs/`. | `summary.html` contains charts and logs. |
| TC-08 | Strategy Override | Path to custom JSON. | 1. `la run --strategy custom.json` | Agent logs use of custom.json params. |
| TC-09 | Graceful Shutdown | Session running. | 1. Send SIGINT (Ctrl+C). | Final report written, orders cancelled. |
| TC-10 | Trailing Stop Activation | Position + profit. | 1. Price moves > trigger. | SL moves up to lock in profit. |

### Group 2: Edge Cases (Boundary Conditions)
| ID | Title | Preconditions | Steps | Expected Result |
| :--- | :--- | :--- | :--- | :--- |
| TC-11 | Zero Balance Start | Acc balance $0. | 1. Start session. | Error logged: "Insufficient Margin". No crash. |
| TC-12 | Max Spread Breach | High volatility. | 1. Spread exceeds threshold. | Order blocked by Risk Sentinel. |
| TC-13 | Partial Fills | Live trading. | 1. Order partially filled. | System tracks remaining qty correctly. |
| TC-14 | Precise TP/SL Match | Price hits SL to the cent. | 1. Set SL at 40k. 2. Feed price 40k. | Exit triggered exactly at 40k. |
| TC-15 | Duplicate Signal | Two identical signals. | 1. Send same signal ID twice. | System ignores second signal (Idempotency). |
| TC-16 | Leap Year Date | Date is Feb 29. | 1. Run backtest on Feb 29. | No date/time parsing errors. |
| TC-17 | WebSocket Reconnect | Net drops for 30s. | 1. Kill connection. 2. Observe. | Agent reconnects and resumes without state loss. |
| TC-18 | Min Order Size | Tiny position size. | 1. Risk < Min Lot. | Rejected with "Size too small" warning. |
| TC-19 | Overlapping Runs | Run session A. Start B. | 1. `la run`. 2. `la run` again. | Second run fails via file locking. |
| TC-20 | Capped Daily Loss | Loss hit $50. | 1. Intentionally lose $50. | Kill switch flips. All trading stops. |

### Group 3: Negative/Error Scenarios
| ID | Title | Preconditions | Steps | Expected Result |
| :--- | :--- | :--- | :--- | :--- |
| TC-21 | Corrupt Config JSON | Delete a bracket. | 1. Start agent. | Clean error: "Invalid JSON in config". |
| TC-22 | Invalid API Secret | Typo in `.env`. | 1. Run `la doctor`. | Returns [FAIL] for Bitunix Auth. |
| TC-23 | WebSocket Timeout | Freeze main loop. | 1. Mock network freeze. | Heartbeat fails, `la watch` restarts process. |
| TC-24 | Negative Stop Loss | Stop > Entry (Long). | 1. Force invalid SL. | RiskSentinel blocks order creation. |
| TC-25 | Large Order Rejection | Order > $200k. | 1. Try huge risk size. | Rejected by Safety Gates. |
| TC-26 | File System Full | disk space 0. | 1. Try to save log. | Log failure handled gracefully (no crash). |
| TC-27 | Unknown Symbol | `--symbol DOGE`. | 1. Start agent. | Error: "Token not supported by provider". |
| TC-28 | Multiple Kill Switches | Env and file. | 1. Set both to TRUE. | System stays halted until BOTH are FALSE. |
| TC-29 | Delayed Data | Data lag > 60s. | 1. Feed stale ticks. | Error: "STALE DATA" trigger restart. |
| TC-30 | Parallel Command Conflict | `la start` + `la doctor`. | 1. Run simultaneously. | CLI locks prevent race conditions. |

### Group 4: Data Integrity & Concurrency
| ID | Title | Preconditions | Steps | Expected Result |
| :--- | :--- | :--- | :--- | :--- |
| TC-31 | Checkpoint Recovery | Crash during trade. | 1. Pull plug. 2. Restart. | System finds trade in state, resumes tracking. |
| TC-32 | Log Rotator | Generate 1GB logs. | 1. Continuous logging. | Logs rotate, no infinite disk growth. |
| TC-33 | Event Stream Ordering | High freq ticks. | 1. Check `events.jsonl`. | Every event is strictly chronological. |
| TC-34 | Atomic State Write | Kill during write. | 1. Kill -9 during `save()`. | Next boot uses last GOOD checkpoint. |
| TC-35 | Secret Scrubbing | API Keys in logs. | 1. Grep "KEY" in logs. | Keys are masked (e.g., `****1234`). |

### Group 5: UI & Reporting
| ID | Title | Preconditions | Steps | Expected Result |
| :--- | :--- | :--- | :--- | :--- |
| TC-36 | HTML Chart Zoom | View report. | 1. Click zoom on chart. | Plotly chart responds correctly. |
| TC-37 | Dashboard Auth | API access. | 1. Access `/api/status`. | Returns valid JSON structure. |
| TC-38 | Mobile Dashboard | Open on phone. | 1. View /dashboard. | Responsive layout fits small screen. |
| TC-39 | Dark Mode Toggle | UI preference. | 1. Click theme toggle. | CSS updates without page reload. |
| TC-40 | CSV Data Match | Export trades. | 1. Compare CSV vs DB. | No missing trades in export. |

### Group 6: Permissions & Security
| ID | Title | Preconditions | Steps | Expected Result |
| :--- | :--- | :--- | :--- | :--- |
| TC-41 | Read-Only API Key | RO key in env. | 1. Attempt trade. | Fails at Broker level: "Unauthorized". |
| TC-42 | Path Injection | `--strategy ../../etc/`. | 1. Run command. | Blocked by path validation. |
| TC-43 | Env Var leakage | Check logs. | 1. Log environment. | Critical secrets omitted. |
| TC-44 | SQL/Command Inject | Symbol = `; rm -rf`. | 1. Input bad symbol. | Sanitized, command ignored/failed safely. |
| TC-45 | Dependency Audit | `safety check`. | 1. Run audit. | 0 critical vulnerabilities in libs. |

### Group 7: Performance & Stress
| ID | Title | Preconditions | Steps | Expected Result |
| :--- | :--- | :--- | :--- | :--- |
| TC-46 | Tick Throughput | 1000 ticks/sec. | 1. Load test provider. | Engine latency < 10ms processing. |
| TC-47 | CPU Soak Test | 24h run. | 1. Run session 24h. | No memory leaks, CPU stable < 5%. |
| TC-48 | Multi-Thread Lock | concurrent orders. | 1. Signal storm (10 sigs). | Orders queued/handled without locking up. |
| TC-49 | Startup Latency | Cold start. | 1. Time `la start`. | Fully active in < 3 seconds. |
| TC-50 | DB Recovery Speed | 10k trade history. | 1. Load huge history. | Resume time < 1 second. |

---

## 4. Non-Functional Testing

### A. Performance Metrics
- **Max Latency**: Tick-to-Signal < 50ms.
- **Memory Ceiling**: < 200MB RAM usage for long-running sessions.
- **Disk I/O**: Efficient append-only logging to minimize SSD wear.

### B. Security Checklist
- [ ] No plaintext secrets in code or git history.
- [ ] TLS verification for all API calls.
- [ ] Sanitize all CLI inputs using `typer`.
- [ ] Implement `LOG_LEVEL` filtering to prevent trace leakage in prod.

### C. Accessibility & Compatibility
- **UI**: WCAG 2.1 AA compliant (color contrast for status indicators).
- **Browsers**: Chrome, Firefox, Safari (mobile/desktop).
- **OS**: Windows (primary), Linux/WSL (secondary/server).

---

## 5. Automation Plan

### Strategy: "Pyramid of Confidence"
1. **Unit (70%)**: Fast, offline tests for indicators and risk math.
2. **Integration (20%)**: Mock-provider sessions validating agent communication.
3. **E2E (10%)**: `la run --mode selftest` targeting the Bitunix API with tiny size.

### Tooling
- **Backend**: `pytest` + `pytest-asyncio`.
- **UI**: `playwright` (if live dashboard complexity increases).
- **CI**: GitHub Actions (lint, unit, integration on every PR).

---

## 6. Bug Workflow

### Severity Levels
- **S1 (Blocker)**: Direct financial risk, data loss, or system crash.
- **S2 (Critical)**: Core feature broken (e.g., cannot take profit).
- **S3 (Normal)**: UI glitch, log format issue.
- **S4 (Enhancement)**: Refinement request.

### Release Blocker Rules
1. Any S1 or S2 bug open.
2. Code coverage < 85% on Risk/Broker modules.
3. Failing `la doctor` check.

---

## 7. Exit Criteria (Go/No-Go Checklist)
- [ ] 100% of P0/P1 Test Cases PASSED.
- [ ] `la run --mode selftest` passes on live Bitunix connection.
- [ ] Security audit (secrets/permissions) complete.
- [ ] Documentation updated to match current CLI version.
- [ ] Monitoring dashboard verified for long-run stability (2h soak).

---

## Next Actions for User
1. **Review**: Approve the test case list and priorities.
2. **Execute Smoke**: Run `pytest tests/test_smoke.py` to verify baseline.
3. **Initialize Automation**: Decide if we should add Playwright for UI testing now.
4. **Sub-Account Setup**: Create a Bitunix sub-account for live integration testing.
