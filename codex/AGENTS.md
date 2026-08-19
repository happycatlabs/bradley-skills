# Global Codex Guidance

## Fable PR Authorship

When working in `happycatlabs/fable`, every agent- or automation-owned pull
request must be created or explicitly adopted with the installed `fable-pr`
command.

Dancer is a brokered GitHub App, not a login expected in `gh auth status`. Do
not fall back to `ratley`, `eve-senara`, or another human account because
Dancer is absent from the local GitHub CLI identities. Plain `gh pr create` is
allowed only when Bradley explicitly requests personal authorship.

New PRs open as drafts. After `fable-pr` returns verified Dancer authorship and
the exact head, keep the PR draft while following Fable's `claim` and `attest`
steps. Then run `fable-pr ready --repo happycatlabs/fable --pr <number>` before
starting `watch`. The helper does not grant approval, merge, deploy, release,
tracker, or production authority.
