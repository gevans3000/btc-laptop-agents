# GATES.md — Safety & Validation

> **STATUS**: BLUEPRINT (Target for v1.1)
> **PURPOSE**: Definitions of quality gates that prevent bad trades.

## 1. Candle Integrity Gate
**When**: After Data Stage.
**Checks**:
*   **Freshness**: Last candle is within `2 * interval` of `now`.
*   **Continuity**: No timestamp gaps > `interval`.
*   **Validity**: `High >= Low`, `Volume >= 0`.
**Action on Fail**: Abort run, Log `DataQualityError`.

## 2. Feature Sanity Gate
**When**: After Feature Stage.
**Checks**:
*   **Completeness**: All required indicators (SMA10, SMA30) present.
*   **Bounds**: Values are finite (no `inf`, `NaN`).
**Action on Fail**: Abort run, Log `CalculationError`.

## 3. Trade Schema Gate
**When**: After Strategy Stage.
**Checks**:
*   **Signal**: Must be one of `["BUY", "SELL", "HOLD"]`.
*   **Direction**: `BUY` requires `close > fast_sma > slow_sma` (logic check).
**Action on Fail**: Force `HOLD`, Log `LogicMismatch`.

## 4. Risk Invariant Gate (CRITICAL)
**When**: After Risk Stage.
**Checks**:
*   **Position Size**: `risk_amount <= account_equity * 0.01` (1% hard limit).
*   **Stop Loss**: MUST be present.
*   **Take Profit**: MUST be present.
*   **Ordering**:
    *   Long: `Stop < Entry < TP`.
    *   Short: `TP < Entry < Stop`.
**Action on Fail**: Abort Order, Log `RiskViolation`.

## 5. Execution Determinism Gate
**When**: After Execution Stage.
**Checks**:
*   **Slippage**: Fill price is within allowed variance of decision price.
*   **Fills**: `Quantity` matches `Order.Quantity`.
**Action on Fail**: Log `ExecutionDrift` (Simulation warning).
