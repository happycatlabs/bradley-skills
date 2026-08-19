# Fable Dancer PR Helper

Use the installed `fable-pr` command for every agent- or automation-owned Fable
pull request. Creation is deliberately draft-first:

```sh
fable-pr create \
  --repo happycatlabs/fable \
  --base master \
  --head codex/fable-123 \
  --title "Fix FABLE-123" \
  --body "Closes FABLE-123." \
  --label "Client Release"
```

The `create` word is optional for compatibility with existing agent prompts.
New pull requests still open as drafts either way.

## Exact-number broker adoption

An automation that has already created a Dancer-authored Fable draft can ask
the token-owning broker to adopt only that exact pull request generation:

```json
{
  "action": "adopt-exact",
  "input": {
    "repo": "happycatlabs/fable",
    "number": 123,
    "base": {
      "ref": "master",
      "sha": "<40-character-base-sha>"
    },
    "head": {
      "ref": "codex/fable-123",
      "sha": "<40-character-head-sha>"
    }
  }
}
```

This is a broker action, not a branch-searching CLI shortcut. After minting the
Dancer installation token, it performs only exact REST GET readbacks. It
requires an open, unmerged Fable draft with the canonical PR URL, the exact
Dancer login and actor ID, Fable's numeric and named repository identity on both
base and head, the expected base and head generation, and the same exact remote
head. It then re-reads the numbered PR before returning this strict proof shape:

```json
{
  "repo": "happycatlabs/fable",
  "number": 123,
  "url": "https://github.com/happycatlabs/fable/pull/123",
  "author": {
    "login": "dancer-automation[bot]",
    "actorId": 266699010
  },
  "base": "master",
  "baseSha": "<40-character-base-sha>",
  "head": {
    "ref": "codex/fable-123",
    "sha": "<40-character-head-sha>"
  },
  "draft": true,
  "adopted": true,
  "exactGenerationVerified": true
}
```

`adopt-exact` never lists pull requests by branch, creates a fallback pull
request, applies labels, marks a draft ready, or reads or mutates owner state.
A missing, closed, ready, merged, forked, stale, malformed, or otherwise
mismatched response fails closed without a pull-request mutation.

The same broker explicitly allows `happycatlabs/fable-incident-daemon`.
Daemon PRs use the normal `create` command, then move to ready only after the
caller supplies the exact validated head:

```sh
fable-pr ready-daemon \
  --repo happycatlabs/fable-incident-daemon \
  --pr <number> \
  --head <40-character-sha>
```

This path does not invent Fable's repository-local claim or attestation
metadata. It verifies Dancer authorship, `master` as the base, and the exact
head immediately before and after the ready transition.

Install the stable command once per machine:

```sh
ln -sfn "$HOME/dev/bradley-skills/bin/fable-pr" "$HOME/.bun/bin/fable-pr"
```

On Eve, replace `$HOME/dev` with `$HOME/code`. The launcher invokes Bun by
absolute path, so it works even when an ad-hoc agent shell does not include
`$HOME/.bun/bin` in `PATH`.

Repeat `--label` for additional labels. If the head already has an open pull
request, the command fails unless `--adopt` is supplied. Adoption still requires
the existing pull request to be Dancer-authored and to point at the exact
requested head; it may adopt an older ready PR without changing that PR's draft
state.

On Eve, the helper reads the existing Dancer GitHub App configuration and keeps
the short-lived installation token in process memory. On Bradley's laptop it
runs the token-owning broker through `ssh eve`; the token never leaves Eve.
Only after the returned PR author and head proof passes does the caller's
ambient human `gh` credential apply labels.

After creation, run Fable's protected owner flow while the PR is still a draft:

1. `claim` the exact PR and head.
2. `attest` the originating task and Linear ticket.
3. Mark the PR ready with Dancer:

```sh
fable-pr ready \
  --repo happycatlabs/fable \
  --pr 123
```

`ready` reads the Dancer-authored owner comment and requires one matching passed
task attestation for the current PR, base, and head. Missing, duplicate,
malformed, foreign-edited, failed, or stale ownership evidence stops before the
ready-for-review mutation. Calling it again is safe: an already-ready PR is
returned only after the same ownership checks pass.

Do not push while `ready` is running. GitHub does not offer an atomic
"mark this exact head ready" operation, so the helper rechecks immediately
before and after the transition and fails if the generation changed during that
small API window.

Then start the normal `watch` loop. This ordering lets the first trusted review
run collect its Linear and owner context instead of racing the claim.

The helper grants no approval, merge, deploy, release, tracker, or production
authority. It enforces the ordering around Fable's existing
`claim` / `attest` / `watch` owner loop; it does not replace that loop.

For an explicitly personal, interactive PR, Bradley may choose plain
`gh pr create`. Agents must not infer that choice.

Focused test:

```sh
bun test scripts/fable-pr.test.ts
```
