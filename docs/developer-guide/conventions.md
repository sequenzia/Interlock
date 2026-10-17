# Conventions

The rules the codebase follows, so a change reads like the code around it. CLAUDE.md at the repo root is the short version that tooling reads; this page explains the same rules with their reasons.

## Python

- **Formatting and linting** are ruff's job: `uv run ruff format backend tests && uv run ruff check backend tests`. The rule set in `pyproject.toml` is `E, F, I, UP, B, W, ANN, RUF` with `ANN401` and `E501` ignored (ruff format owns layout; `E501` would fire only on unbreakable strings). Line length is 100, target `py312`.
- **Type hints on every function**, including private helpers and tests' production counterparts. `ANN` is relaxed for `tests/**` only.
- Every module starts with `from __future__ import annotations` and a docstring that says what the module is for and which part of the design it implements.
- **Dataclasses for values**: `Thresholds`, `Decision`, `RankedAction`, `Escalation`, `Zone`, `Constraint`, `CheckResult`, `Exchange`. Frozen where the value is a result rather than a mutable record.
- **Pure functions where the logic matters.** `shield.decide` and `resolve` take the ranking and the probability grid and return a `Decision`; no simulator, no network, so every branch has a unit test. The same holds for `checkers.label`, `metrics.episode_metrics` and `facts.sentences`.
- Modules behind a subcommand expose `add_arguments(parser)` and `run_cli(args) -> int`, and keep a `main()` so `python -m backend.<module>` matches `interlock <command>`.
- `backend/paths.py` holds the repo-relative paths the modules share (models, logs, internal, the `.env` file). The spike computes its own from `__file__`.

## TypeScript

- `strict` plus `noUncheckedIndexedAccess`, `noUnusedLocals` and `noUnusedParameters`; `pnpm typecheck` must pass and runs ahead of `vite build`.
- Filenames are kebab-case: `approval-queue.tsx`, `ws-client.ts`.
- One Zustand store with slices. Components subscribe with one field per selector and never mirror server state into `useState`; local state is for inputs before commit and for display clocks only.
- Selectors return stable references. Never `?? []` or `?? {}` inside a selector; hoist a module constant and apply the fallback outside. See [Store and selectors](frontend/store.md).
- Tailwind utilities inline, plus the six shared classes in `styles.css` (`panel`, `panel-title`, `btn`, `btn-primary`, `chip`, `badge`). No component library.
- `types.ts` is a hand-maintained mirror of the backend's record and protocol and changes only after the backend does.

## Naming

| Thing | Convention |
| --- | --- |
| The project | Interlock. Appears in the page title, the header, the package name and the CLI |
| The mechanism | shield, lowercase, in prose, flags (`--shield on`), record fields (`shield_on`) and module names. Never a product name |
| Lanes | Numbered from the left starting at 1, everywhere a human or Jev reads them. highway-env's zero-based `lane_index` is converted once in `facts.lane_number` |
| Units | In the field name: `speed_mps`, `vehicle_ahead_gap_m`, `latency_ms`, `cost_usd`, `starts_in_m` |
| Constraint ids | `c1`, `c2`, ... assigned by `ConstraintStore` and stable for the session |
| Run ids | `<UTC stamp>_seed<N>_<on|off>`, for example `2026-10-18T14-02-11_seed7_on`; also the JSONL filename |
| Eval labels | `<on|off>_ta<t_allow>_tb<t_block>` with an optional `_zone<N>` suffix |
| Decisions | `allow`, `fallback`, `escalate`, `all_blocked` in code and records; `DECISION_LABEL` maps them to UI words |
| Judge sources | `live`, `cache`, `unavailable` |

## Writing

- No em dashes or en dashes anywhere: docs, UI copy, commit messages. Use a comma, a colon or a period.
- Jev questions are positive assertions with the rule text quoted verbatim. No negation in instructions or criteria. Operators may type negated rules; the console suggests a positive rephrase and keeps their text.
- UI copy is lowercase and short, matching the dense console style: "waiting on operator", "back to live", "drop work zone ahead".
- Docstrings and comments say why, not what, and cite the part of the design they implement when it is not obvious from the code.

## Git

Conventional Commits, `type(scope): description`, with the types used in the history: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`. Scopes seen so far: `backend`, `console`, `eval`, `cli`, `deploy`, `readme`, `internal`; a scope is optional. Examples from the log:

```text
feat(cli): add the interlock command with run, eval, train, spike and console
refactor: rename project to Interlock, keep shield as the technical term
feat(deploy): console on Vercel, backend container on Fly.io
```

Do not commit or push unless asked. The main branch is `main`.

## Process rules

- **Keep the headless CLI working at all times.** The server and the console sit on top of `EpisodeRunner`, not beside it. A feature that only works in the browser is incomplete.
- **The record is a contract.** Change the contract page, then `backend/logger.py`, then `frontend/src/types.ts`, in that order. See [Log record](contracts/log-record.md).
- **`.dockerignore` is an allowlist.** A new file the server reads at runtime must be added there and copied in the `Dockerfile`, or the deployed backend will not see it. See [Deployment internals](deployment-internals.md).
- **Secrets.** `TYPESAFE_API_KEY` lives in `backend/.env` locally and in a Fly secret in production. It is never logged, never written to a record, never in `fly.toml` and never in the image.
- **Numbers come from runs.** Latency, cost, violations and calibration are quoted from `interlock eval` output and `interlock spike` output, not estimated.
- **Library docs** come from the official sites (highway-env, Stable-Baselines3, TypeSafe); Context7 is disabled for this project.

`internal/` holds the project's planning history and the evaluation report; it is not part of this documentation.
