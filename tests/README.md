# Test Suite Notes

Tests in this folder cover solver correctness, propagation behavior, runtime guardrails, and backend regressions.

## Typical run

```bash
python3 -m pytest -q
```

## Focused runs

```bash
python3 -m pytest -q tests/test_cp_search.py tests/test_cp_propagation.py
python3 -m pytest -q tests/test_runtime_limits.py tests/test_restart_limits.py
```

If `pytest` is not installed in your local environment yet, install dev dependencies first.
