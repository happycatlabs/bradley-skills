# Claude and Cursor CLI orchestration benchmark

Runs exactly ten unique agents (five Claude, five Cursor) against generated
fixture repositories. It measures read-only discipline, structured results,
resume identity, live-session inspection, scoped implementation, and
concurrency.

```bash
python3 benchmarks/cli-orchestration/run_benchmark.py

# Later, from the Codex CLI TUI:
python3 benchmarks/cli-orchestration/run_benchmark.py --host-surface codex-cli-tui
```

Each run writes a manifest, per-lane raw evidence, a scorecard, and a compact
report under `benchmarks/runs/<timestamp>/`. The default manifest records
`host_surface: codex-desktop`; the flag changes only the host label for the
Codex CLI TUI comparison while preserving prompts, fixtures, models, and gates.
