---
name: apple-containers
description: Use when working with Apple's `container` CLI on macOS, especially to run isolated smoke tests, disposable Linux labs, port-published services, or container-machine experiments. Trigger when the user mentions apple/container, Apple Container, `container run`, `container machine`, isolated test harnesses, snapshots/checkpoints for container work, or asks whether Apple Container should be used instead of Docker/worktrees.
metadata:
  short-description: Apple Container isolation and test harness guidance
---

# Apple Containers

Use Apple's `container` CLI as an optional isolation primitive. Prefer it for scary smoke tests, disposable Linux command environments, and proofing host-safety. Do not quietly make it the default runtime for local product development.

## First Checks

Start by verifying the installed CLI and reading live help when command details matter:

```bash
command -v container
container --version
container --help
container run --help
container machine --help
```

If `container` is missing, do not invent a fallback. Explain that this path needs Apple Container installed, then use the existing host-safe approach for the task.

## Core Posture

- Use Apple Container as an outer harness around risky operations, not as a required dependency for normal workflows.
- Keep normal unit tests fast on the host with temp dirs, fake repos, temp homes, and no product services.
- Use containers when a command bug could start/stop host services, mutate local worktrees, collide on ports, or pollute local state.
- Prefer worktrees for source-code isolation during normal agent work. Prefer Apple Container for disposable verification of tooling behavior.
- Do not assume Apple Container can snapshot or restore a machine. The observed CLI has no first-class `machine snapshot` or `machine restore` command.
- Do not depend on private Apple Container storage internals for durability.

## Spike Findings To Preserve

These are the important lessons from an Apple Container tooling spike:

- `container machine` is good for a persistent Linux command environment, but it is not a supported checkpoint/restore primitive.
- `container export` exports containers, not stopped machine state. Do not treat it as machine snapshot support.
- Machine state lives under Apple-owned app support storage. Treat paths under `~/Library/Application Support/com.apple.container` as implementation details, not an API.
- Machine root filesystems can be sparse with large logical sizes. Check real disk usage before panicking, but still surface stale/large workspace warnings.
- A bare Alpine/Ubuntu image is usually not enough for a polyglot project. If repeated container testing becomes useful, prefer a small project base image with the required runtimes, git, and common shell tools.
- Apple Container helps most with host blast-radius reduction. It does not automatically solve shared local database state, fixed localhost assumptions, or cross-service URL drift.
- For browser-facing services in containers, bind inside the container to `0.0.0.0` and publish the host port explicitly.
- If exact machine snapshot/restore becomes important, look for an upstream Apple-supported feature or proposal. Do not fork Apple Container or copy private storage as a project solution.

## Good Uses

- Test CLI commands that might otherwise touch host services, such as `up`, `restart`, `stop`, `workspace destroy`, install/update, or cleanup flows.
- Run a clean Linux smoke environment with a mounted repo and temporary home.
- Validate port-published services without claiming common host ports permanently.
- Compare behavior in a clean machine/container when the host environment may be polluted.
- Build or run a project base image for repeatable test dependencies.

## Poor Uses

- Replacing worktrees as the default source workspace.
- Running a multi-service stack locally by default before port, database, and service-URL ownership are solved.
- Hiding host mutations behind a container wrapper while still mounting broad host directories read-write.
- Treating container machines as durable checkpoints unless Apple adds a supported snapshot/restore workflow.
- Using private bundle paths under `~/Library/Application Support/com.apple.container` as an API.

## Running A Mounted Repo

For a disposable test of a trusted local repo:

```bash
container run --rm \
  --volume "$PWD":/workspace/project \
  --workdir /workspace/project \
  --env PROJECT_HOME=/tmp/project-home \
  oven/bun:1 \
  bun run check
```

Use `--volume` only for paths the test needs. Prefer mounting the repo read-only when the command should not write to it:

```bash
container run --rm \
  --mount type=bind,source="$PWD",target=/workspace/project,readonly \
  --workdir /workspace/project \
  oven/bun:1 \
  bun test
```

If the test must mutate a repo, prefer cloning into the container or mounting a disposable worktree instead of the user's main checkout.

## Publishing Ports

Use `--publish` when browser or host access is needed:

```bash
container run --rm \
  --publish 3011:3000 \
  --workdir /workspace/app \
  <image> \
  bun run dev -- --host 0.0.0.0 --port 3000
```

Inside containers, bind services to `0.0.0.0`, not only `localhost`, if the host needs to reach them through published ports.

## Container Machines

Machines are useful for persistent Linux command environments:

```bash
container machine create ubuntu:24.04 --name project-lab
container machine run -n project-lab -- uname -a
container machine set -n project-lab cpus=4 memory=8G home-mount=ro
container machine stop project-lab
container machine delete project-lab
```

Use machines when you want a named environment that survives between commands. Use `container run --rm` when you want a one-shot disposable process.

## Host Safety Rules

- Before running a command inside a container, identify which host paths are mounted read-write.
- Use temp homes such as `/tmp/project-home` for local tool state.
- Avoid mounting `~`, `~/.ssh`, `~/.config`, or product repo parents unless explicitly needed.
- Use `--ssh` only when the task truly needs GitHub/private repo access.
- Use `--rm` for disposable tests so stopped containers do not accumulate.
- Use `container list`, `container machine list`, `container image list`, and `container volume list` to inspect local state before cleanup.
- Do not run `container prune` or broad deletes without explicit user approval.

For space checks, prefer observation first:

```bash
container list
container machine list
container image list
container volume list
du -sh ~/Library/Application\ Support/com.apple.container 2>/dev/null
```

Warn about stale or large state. Do not automatically prune/delete state unless the user explicitly asks.

## Project Tooling Guidance

For a host-first workspace manager or project CLI, Apple Container is best as an optional self-test isolation backend:

- Keep the tool host-first and usable without Apple Container.
- Make dangerous commands safe on the host first, then optionally verify them in Apple Container.
- A command shape like `tool self-test isolation=apple-container` is reasonable.
- Container-backed self-tests should use a temporary home, fake repos or disposable worktrees, and narrow mounts.
- Use Apple Container for dangerous command smoke tests: `up`, `restart`, `stop`, `workspace destroy`, install/update, and cleanup behavior.
- Do not use Apple Container to paper over unsafe CLI semantics. Fix the host-safe behavior first, then verify it in isolation.

If a command accepts `dry_run=true`, it must not execute real start/stop/destroy behavior on either host or container. Apple Container can reduce blast radius, but it is not a substitute for correct dry-run semantics.

## Relationship To Worktrees And DBs

Use the right isolation primitive:

- Worktrees isolate source and branches well. Keep them as the default for multi-agent repo work.
- Workspace metadata should own ports, process ownership, repository paths, and warnings.
- DB snapshots or separate DB instances are the right tool for database state. Apple Container alone does not isolate the shared host Postgres/Redis/Temporal stack unless those services also run inside the container environment.
- A canonical host backend stack is still pragmatic when dependent services have fixed localhost assumptions. Use Apple Container around tooling tests until services support clean per-workspace ports and URLs.

## Snapshot And Checkpoint Language

Be precise:

- Use "workspace snapshot" for inspectable source evidence such as diffs, branch/head, and skipped files.
- Use "DB snapshot" for database dumps or database restore points.
- Reserve "checkpoint" for something with real restore semantics, or explicitly say restore is not supported.
- Do not imply Apple Container machine snapshots exist unless the installed CLI proves they do.

## Decision Heuristic

Ask: "What blast radius am I trying to reduce?"

- Source-code isolation: use git worktrees.
- Local DB state isolation: use DB snapshots or separate DB instances.
- Process/port/start-stop safety: Apple Container can help.
- Clean dependency environment: Apple Container can help.
- Default day-to-day local dev: stay host-first unless the user explicitly wants containerized work.
