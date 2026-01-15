# Automated Troubleshooting Guide

> **Note**: This document is auto-generated from the Agent's Learning Debugger knowledge base.
> **Last Updated**: 2026-01-15 16:26:21

## Table of Contents

1. [92872f70627c32a4](#issue-92872f70627c32a4)
2. [29a1ad283cc792b4](#issue-29a1ad283cc792b4)
3. [b854ff3e2f292317](#issue-b854ff3e2f292317)

---

## Issue: 92872f70627c32a4 <a id='issue-92872f70627c32a4'></a>

**Last Seen**: 2026-01-15T15:10:11.127279 | **Occurrences**: 3

### Error Signature
```text
Error in on_candle_closed: cannot access local variable 'append_event' where it is not associated with a value
```

### Root Cause
Circular import refactoring caused UnboundLocalError

### Solution
> Fixed import placement of append_event in async_session.py

---

## Issue: 29a1ad283cc792b4 <a id='issue-29a1ad283cc792b4'></a>

**Last Seen**: 2026-01-15T15:12:08.753289 | **Occurrences**: 3

### Error Signature
```text
Error in on_candle_closed: [WinError 5] Access is denied: 'tests\\stress\\run_data\\unified_state.tmp' -> 'tests\\stress\\run_data\\unified_state.json'
```

### Root Cause
High frequency file writes on Windows caused locking contention

### Solution
> Used dry_run=True to skip file persistence in stress tests

---

## Issue: b854ff3e2f292317 <a id='issue-b854ff3e2f292317'></a>

**Last Seen**: 2026-01-15T15:18:54.396384 | **Occurrences**: 176

### Error Signature
```text
Error checking for gaps: invalid literal for int() with base 10: '2025-01-01T00:00:00Z'
```

### Root Cause
MockProvider was returning ISO format strings while AsyncRunner Expected integer strings for gap detection.

### Solution
> Fixed MockProvider to return unix timestamp strings consistent with AsyncRunner expectations.

---
