# Critique signal benchmark

Measures whether the current `critique` skill selects relevant repository
context and admits only source-backed findings. The runner creates a disposable
generic CLI repository with:

- an actual exit-status defect,
- explicit CLI and test-tier guidance,
- unrelated UI guidance in an untouched directory, and
- harmless performance bait over a constant three-item collection.

```bash
python3 benchmarks/critique-signal/run_benchmark.py
```

The benchmark uses one read-only Claude lane and deterministic host-side gates.
There is no LLM judge, severity score, project-specific fixture, or multi-provider
comparison. Unit tests exercise fixture construction and scoring without making
a model call:

```bash
python3 -m unittest benchmarks/critique-signal/test_run_benchmark.py
```

Each live run writes the fixture diff, raw model evidence, scorecard, and report
under `benchmarks/runs/<timestamp>-critique-signal/`.
