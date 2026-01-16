# Improvement Backlog for 10-Minute Autonomous Paper Trading

## Priority: Autonomy

1. **Why**: Enable single-command start and stop for autonomous operation.
   **What**: Add a `--duration` flag to `run.py` to specify the session duration in minutes. Update `AsyncRunner` to respect this duration.
   **Acceptance**: Run `python -m src.laptop_agents.run --mode live-session --duration 10` and verify it stops after 10 minutes.

2. **Why**: Ensure clean shutdown on duration completion.
   **What**: Implement graceful shutdown in `AsyncRunner.run()` to close positions and save state before exiting.
   **Acceptance**: Verify all positions are closed and state is saved in `final_report.json` after duration expires.

3. **Why**: Handle disconnects and API hiccups gracefully.
   **What**: Enhance `BitunixWSProvider` with automatic reconnection logic and exponential backoff.
   **Acceptance**: Simulate a disconnect and verify the system reconnects and continues trading.

4. **Why**: Survive malformed ticks and data inconsistencies.
   **What**: Add validation and error handling in `market_data_task()` to filter out malformed ticks.
   **Acceptance**: Inject malformed ticks and verify the system logs warnings but continues running.

5. **Why**: Support restart mid-run with state recovery.
   **What**: Implement checkpointing in `StateManager` to save and restore session state.
   **Acceptance**: Kill the process mid-run, restart, and verify it resumes from the last checkpoint.

## Priority: Ease of Management

6. **Why**: Minimize custom coding for configuration changes.
   **What**: Move all configurable parameters to `config/strategies/*.json` and support environment variables.
   **Acceptance**: Change risk parameters via `config/strategies/default.json` and verify they are applied.

7. **Why**: Provide sane defaults for out-of-the-box operation.
   **What**: Update `config/default.json` with conservative defaults for risk, fees, and slippage.
   **Acceptance**: Run without custom config and verify it uses defaults from `config/default.json`.

8. **Why**: Simplify the run workflow with a single command.
   **What**: Create a `Makefile` target or shell script for one-command run and validation.
   **Acceptance**: Run `make run` and verify it starts the session and stops after 10 minutes.

9. **Why**: Enable configuration via CLI flags for quick adjustments.
   **What**: Extend `argparse` in `run.py` to support all key parameters as CLI flags.
   **Acceptance**: Override config parameters via CLI flags and verify they take precedence.

10. **Why**: Support Docker for reproducible runs.
    **What**: Update `Dockerfile` to include all dependencies and entry point for running the session.
    **Acceptance**: Build and run the Docker image with `docker run --rm -it btc-laptop-agents --duration 10`.

## Priority: Reliability

11. **Why**: Prevent excessive losses with circuit breakers.
    **What**: Enhance `TradingCircuitBreaker` to include max daily drawdown and consecutive loss limits.
    **Acceptance**: Simulate losses and verify the circuit breaker trips and stops trading.

12. **Why**: Ensure deterministic stop conditions.
    **What**: Add explicit stop conditions in `AsyncRunner` for max losses, max trades, and duration.
    **Acceptance**: Verify the session stops when any stop condition is met.

13. **Why**: Handle rate limits and backpressure gracefully.
    **What**: Implement rate limiting in `BitunixWSProvider` and `BitunixFuturesProvider`.
    **Acceptance**: Simulate rate limits and verify the system respects them without crashing.

14. **Why**: Validate configuration before starting the session.
    **What**: Enhance `validate_config()` to check all required parameters and fail fast.
    **Acceptance**: Start with invalid config and verify it fails with a clear error message.

15. **Why**: Ensure safe state handling for positions and orders.
    **What**: Implement atomic state persistence in `StateManager` for broker and circuit breaker state.
    **Acceptance**: Kill the process mid-trade and verify state is recovered correctly on restart.

## Priority: Execution Realism

16. **Why**: Simulate realistic execution latency.
    **What**: Add configurable latency simulation in `execution_task()`.
    **Acceptance**: Set latency via config and verify trades are executed with the specified delay.

17. **Why**: Support live market data ingestion.
    **What**: Ensure `BitunixWSProvider` is the default for live sessions and handles real-time data.
    **Acceptance**: Run with `--source bitunix` and verify it connects to the WebSocket and processes ticks.

18. **Why**: Provide fallback data provider for testing.
    **What**: Use `MockProvider` as a fallback when live data is unavailable.
    **Acceptance**: Run with `--source mock` and verify it uses mock data for testing.

## Priority: Observability

19. **Why**: Enable structured logging for debugging.
    **What**: Ensure all critical events are logged with `append_event()` and saved to `events.jsonl`.
    **Acceptance**: Verify `events.jsonl` contains all key events like trades, errors, and heartbeats.

20. **Why**: Generate end-of-run reports for analysis.
    **What**: Enhance `final_report.json` to include PnL, trades, errors, and duration.
    **Acceptance**: Verify `final_report.json` is generated with all required fields after the session.

21. **Why**: Provide minimal metrics for performance tracking.
    **What**: Export metrics to `metrics.json` and `metrics.csv` in `AsyncRunner`.
    **Acceptance**: Verify metrics files are created and contain equity, PnL, and trade data.

## Priority: UX/DevEx

22. **Why**: Simplify setup and operation.
    **What**: Create a `README.md` with clear instructions for running the session.
    **Acceptance**: Follow the instructions in `README.md` and verify the session runs successfully.

23. **Why**: Provide config templates for quick setup.
    **What**: Add template config files in `config/templates/` for different strategies.
    **Acceptance**: Copy a template to `config/strategies/` and verify it works without modifications.

24. **Why**: Enable reproducible runs for testing.
    **What**: Support `--replay` flag to run sessions from recorded `events.jsonl`.
    **Acceptance**: Record a session, then replay it and verify the results match.

25. **Why**: Improve CLI feedback during the session.
    **What**: Enhance `heartbeat_task()` to log progress, equity, and remaining time.
    **Acceptance**: Verify the CLI output includes progress updates every second.

## Priority: Risk Controls

26. **Why**: Enforce max position size.
    **What**: Add `max_position_size` to `RiskConfig` and enforce it in `PaperBroker`.
    **Acceptance**: Set `max_position_size` and verify trades are rejected if they exceed it.

27. **Why**: Implement max loss limit.
    **What**: Add `max_loss_pct` to `RiskConfig` and stop trading if exceeded.
    **Acceptance**: Simulate losses and verify the session stops when `max_loss_pct` is reached.

28. **Why**: Provide a kill switch for emergency stops.
    **What**: Monitor for `kill.txt` in `kill_switch_task()` and stop the session if detected.
    **Acceptance**: Create `kill.txt` during a session and verify it stops immediately.

29. **Why**: Throttle order execution to avoid overloading.
    **What**: Add `max_orders_per_minute` to `RiskConfig` and enforce it in `execution_task()`.
    **Acceptance**: Set `max_orders_per_minute` and verify orders are throttled accordingly.

30. **Why**: Validate all configurations before starting.
    **What**: Enhance `validate_config()` to check all parameters and fail fast.
    **Acceptance**: Start with invalid config and verify it fails with a clear error message.

## Priority: Testing and Validation

31. **Why**: Ensure the system can run unattended for 10 minutes.
    **What**: Test the session with `--duration 10` and verify it completes without errors.
    **Acceptance**: Run `python -m src.laptop_agents.run --mode live-session --duration 10` and verify it stops after 10 minutes.

32. **Why**: Validate the system handles disconnects gracefully.
    **What**: Simulate a disconnect and verify the system reconnects and continues.
    **Acceptance**: Kill the WebSocket connection and verify the system reconnects and resumes trading.

33. **Why**: Ensure the system survives API hiccups.
    **What**: Simulate API errors and verify the system retries and continues.
    **Acceptance**: Inject API errors and verify the system logs warnings but continues running.

34. **Why**: Test the system with malformed ticks.
    **What**: Inject malformed ticks and verify the system filters them out.
    **Acceptance**: Inject malformed ticks and verify the system logs warnings but continues running.

35. **Why**: Validate the system can restart mid-run.
    **What**: Kill the process mid-run and verify it resumes from the last checkpoint.
    **Acceptance**: Kill the process, restart, and verify it resumes trading from the last state.

## Priority: Performance Tuning

36. **Why**: Optimize the async event loop for performance.
    **What**: Profile the async tasks and optimize bottlenecks.
    **Acceptance**: Run the session and verify it processes ticks and executes trades without delays.

37. **Why**: Reduce memory usage for long runs.
    **What**: Limit the candle history window in `AsyncRunner` to 200 candles.
    **Acceptance**: Verify memory usage stays below 500 MB during a 10-minute session.

38. **Why**: Optimize the strategy logic for speed.
    **What**: Pre-initialize `Supervisor` and `AgentState` in `AsyncRunner.__init__`.
    **Acceptance**: Verify the strategy logic runs without delays during the session.

39. **Why**: Minimize disk I/O for state persistence.
    **What**: Batch state saves in `StateManager` to reduce disk writes.
    **Acceptance**: Verify state is saved efficiently without impacting performance.

40. **Why**: Optimize the WebSocket data processing.
    **What**: Profile `market_data_task()` and optimize tick processing.
    **Acceptance**: Verify ticks are processed in real-time without backlog.

## Priority: Documentation

41. **Why**: Document the autonomous run workflow.
    **What**: Update `docs/RUNBOOK.md` with instructions for running autonomous sessions.
    **Acceptance**: Follow the instructions in `docs/RUNBOOK.md` and verify the session runs successfully.

42. **Why**: Provide examples for configuration.
    **What**: Add examples in `config/strategies/` for different risk profiles.
    **Acceptance**: Use an example config and verify it works without modifications.

43. **Why**: Document the CLI flags and environment variables.
    **What**: Update `README.md` with a list of all CLI flags and environment variables.
    **Acceptance**: Verify all CLI flags and environment variables are documented.

44. **Why**: Provide troubleshooting guide.
    **What**: Update `docs/troubleshooting/known_issues.md` with common issues and solutions.
    **Acceptance**: Follow the troubleshooting guide and verify it resolves common issues.

45. **Why**: Document the state recovery process.
    **What**: Update `docs/START_HERE.md` with instructions for recovering from crashes.
    **Acceptance**: Follow the recovery instructions and verify the system resumes correctly.

## Priority: Deployment

46. **Why**: Simplify deployment with Docker.
    **What**: Update `Dockerfile` to include all dependencies and entry point.
    **Acceptance**: Build and run the Docker image and verify it starts the session.

47. **Why**: Provide a one-command run script.
    **What**: Create `scripts/run_autonomous.sh` for starting the session with defaults.
    **Acceptance**: Run `scripts/run_autonomous.sh` and verify it starts the session.

48. **Why**: Enable validation of the session results.
    **What**: Create `scripts/validate_session.sh` to check the session logs and reports.
    **Acceptance**: Run `scripts/validate_session.sh` and verify it validates the session results.

49. **Why**: Support running in cloud environments.
    **What**: Update `Dockerfile` to support cloud deployment with environment variables.
    **Acceptance**: Deploy the Docker image to a cloud environment and verify it runs successfully.

50. **Why**: Enable monitoring of the session.
    **What**: Create `scripts/monitor_session.sh` to monitor the session logs and metrics.
    **Acceptance**: Run `scripts/monitor_session.sh` and verify it monitors the session.

## Priority: Security

51. **Why**: Secure API keys and sensitive data.
    **What**: Use environment variables for API keys and avoid hardcoding.
    **Acceptance**: Verify API keys are loaded from environment variables.

52. **Why**: Validate API keys before starting the session.
    **What**: Add preflight check for API keys in `run.py`.
    **Acceptance**: Start without API keys and verify it fails with a clear error message.

53. **Why**: Ensure safe handling of sensitive data in logs.
    **What**: Scrub sensitive data from logs and reports.
    **Acceptance**: Verify sensitive data is not logged or exposed in reports.

54. **Why**: Validate all inputs to prevent injection attacks.
    **What**: Sanitize all inputs in `run.py` and configuration files.
    **Acceptance**: Inject malicious inputs and verify they are sanitized.

55. **Why**: Ensure secure state persistence.
    **What**: Encrypt sensitive state data in `StateManager`.
    **Acceptance**: Verify sensitive state data is encrypted and secure.

## Priority: Maintenance

56. **Why**: Clean up old runs and logs.
    **What**: Add a cleanup script to remove old runs and logs.
    **Acceptance**: Run the cleanup script and verify old runs and logs are removed.

57. **Why**: Archive session data for long-term storage.
    **What**: Create a script to archive session data to a compressed file.
    **Acceptance**: Run the archive script and verify session data is archived.

58. **Why**: Rotate logs to prevent disk space issues.
    **What**: Implement log rotation in `logger.py`.
    **Acceptance**: Verify logs are rotated and disk space is managed.

59. **Why**: Monitor system health during the session.
    **What**: Enhance `heartbeat_task()` to monitor CPU, memory, and disk usage.
    **Acceptance**: Verify system health is monitored and logged.

60. **Why**: Alert on critical issues during the session.
    **What**: Implement alerts for critical issues like high memory usage or errors.
    **Acceptance**: Trigger a critical issue and verify an alert is generated.

## Priority: Future Enhancements

61. **Why**: Support multiple symbols and intervals.
    **What**: Extend `AsyncRunner` to support multiple symbols and intervals.
    **Acceptance**: Run with multiple symbols and verify they are processed correctly.

62. **Why**: Enable backtesting with historical data.
    **What**: Enhance `backtest` mode to support historical data replay.
    **Acceptance**: Run backtest with historical data and verify the results.

63. **Why**: Support multiple data providers.
    **What**: Extend `CompositeProvider` to support multiple data sources.
    **Acceptance**: Run with multiple data providers and verify they are used correctly.

64. **Why**: Enable multi-strategy trading.
    **What**: Extend `Supervisor` to support multiple strategies.
    **Acceptance**: Run with multiple strategies and verify they are executed correctly.

65. **Why**: Support live trading with real funds.
    **What**: Extend `BitunixBroker` to support live trading with real funds.
    **Acceptance**: Run with live trading and verify trades are executed with real funds.

## Priority: Validation

66. **Why**: Validate the improvement backlog.
    **What**: Review the backlog with stakeholders and prioritize items.
    **Acceptance**: Finalize the backlog and prioritize items for implementation.

67. **Why**: Implement the high-priority items.
    **What**: Start with the top 10 items and implement them.
    **Acceptance**: Verify the top 10 items are implemented and working.

68. **Why**: Test the autonomous session.
    **What**: Run the session with `--duration 10` and verify it completes successfully.
    **Acceptance**: Run `python -m src.laptop_agents.run --mode live-session --duration 10` and verify it stops after 10 minutes.

69. **Why**: Validate the system meets the requirements.
    **What**: Review the system against the requirements and verify all are met.
    **Acceptance**: Confirm the system meets all requirements for autonomous operation.

70. **Why**: Document the final system.
    **What**: Update all documentation to reflect the final system.
    **Acceptance**: Verify all documentation is updated and accurate.
