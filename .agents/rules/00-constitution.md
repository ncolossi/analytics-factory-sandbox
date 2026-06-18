# Workspace rule: follow the constitution

The complete, authoritative rules for this repo are in
[AGENTS.md](../../AGENTS.md). Read and follow it in full before generating or
editing any asset.

Key non-negotiables (see AGENTS.md for the full list, enforced by
`tools/checks/`): Dataform is the only BigQuery writer; never hardcode project
IDs / table names; bronze is append-only; silver & gold need assertions; every
dataset/table/column description is written in **Portuguese**; no secrets in
code; no cross-layer imports.

Run `/review` and `/run-evals` before considering a task done.
