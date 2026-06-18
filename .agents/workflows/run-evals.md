# Run the harness evals

Run the deterministic guardrail self-test and report the result.

```bash
python3 evals/run_evals.py
```

This verifies that (1) every golden exemplar under `evals/golden/` still passes
all checks, and (2) every deliberately-bad fixture under `evals/cases/bad/` still
trips the rule it targets. A failure means either a golden example drifted out of
compliance or a guardrail regressed.

If I ask for a full agent eval, also work through the natural-language golden
tasks in [evals/README.md](../../evals/README.md): perform each task, then run
`python3 tools/checks/run_checks.py` on the output and report the pass rate.
