# Quickstart

Three runs, in order: headless, the console in mock mode, the console live. [Install](install.md) first.

## 1. A headless episode

```bash
uv run interlock run --shield on
```

The first line echoes the configuration:

```text
shield on | seed 0 | jev live | rules ['Speed limit 25 m/s', 'No lane change if a vehicle is within 10 m in the target lane', 'Keep the left lane for passing only'] | thresholds 0.3/0.7 | operator simulated | log backend/logs/runs/2026-10-17T01-27-46_seed0_on.jsonl
```

`jev live` appears when the key is set, otherwise `jev mock`. The three standing rules are the presets minus the lane-closed rule, which only arrives with a zone. The operator is simulated: escalations are answered from the ground-truth checkers.

Then one line per step:

```text
step   3 | lane 2  29.6 m/s | top FASTER     p=0.93 | fallback -> IDLE (c1) | r=0.83 | live 160 ms
```

Reading left to right:

| Field | Meaning |
| --- | --- |
| `step 3` | step index within the episode |
| `lane 2 29.6 m/s` | ego lane (numbered from the left) and speed before the action |
| `top FASTER p=0.93` | the policy's top-ranked action and its worst p(violation) across enabled rules |
| `fallback -> IDLE (c1)` | the decision, the executed action when it differs from the top, and the rule id that fired; an escalation adds `[approve]` or `[deny]` |
| `r=0.83` | task reward for the step |
| `live 160 ms` | where the answers came from (`live`, `cache` or `unavailable`) and the judge latency for the step; `JUDGE UNAVAILABLE` and `CRASH` are appended when they apply |

The run ends with a JSON summary: steps, return, crash, decision counts, violations per rule, human answers, judge sources, latency percentiles, tokens and cost.

Now the same seed with the shield off. The judge and the checkers still run in shadow, so you can compare violations directly:

```bash
uv run interlock run --shield off --seed 3
uv run interlock run --shield on --seed 3
```

And an offline run that drops a work zone in lane 3 at step 10:

```bash
uv run interlock run --jev mock --zone-at-step 10
```

In mock mode, answers come from the cache when it has them. Anything unseen is "judge unavailable" at p = 0.5, which escalates, and the simulated operator answers it. Watch the lane-closed rule appear at step 10 and retire once the zone is behind the ego.

## 2. The console, offline

```bash
uv run interlock console --jev mock --escalation-timeout 0
```

This starts the WebSocket server on port 8000 and the Vite dev server on port 5173, and prints both URLs. Open <http://127.0.0.1:5173>. ++ctrl+c++ stops both.

`--escalation-timeout 0` means an escalation waits for you indefinitely instead of auto-denying after 20 seconds.

1. The status strip shows a green dot, `live` and `jev mock`. The rules panel says "No rules yet".
2. Click the "+ Speed limit 25 m/s" chip. The rule appears with `checker speed_limit`.
3. Press "step" (or ++n++). Each candidate action is judged. If the cache has no answer for this state, the step escalates with a "judge unavailable" badge and the simulation pauses with a "waiting on operator" badge.
4. Read the card in the approval queue: the reason, the proposed action, its facts in plain sentences, the rule and the probability. Press "approve" (++a++) or "deny" (++d++), or press ++1++ to ++5++ to run any candidate from the list. Deny executes the fallback named on the card.
5. Press "play" (++space++) and watch the decisions strip fill in. Click any tick to open the inspector for that step.
6. Click "drop work zone ahead". A hatched zone appears in lane 3 and the lane-closed rule joins the list.

The [console tour](console/tour.md) covers every control.

## 3. The console, live

With `TYPESAFE_API_KEY` in `backend/.env`:

```bash
uv run interlock console --escalation-timeout 0
```

The jev badge reads `jev live`. Steps that hit the cache show `cache` in the strip; new states show `live` with the round-trip latency. Toggle "shield on" to "shield off" and press "reset" to run the same seed unshielded and watch the violations counter.

For development, `uv run interlock console --reload --open` restarts the server on backend changes and opens the browser.

## Where things land

| Path | Contents |
| --- | --- |
| `backend/logs/runs/<stamp>_seed<N>_<on|off>.jsonl` | one record per step for every `interlock run` and every console episode |
| `backend/logs/jev_cache.jsonl` | every Jev answer, keyed by content hash |
| `backend/logs/eval/` | evaluation runs, see [Evaluation and results](evaluation.md) |
| `models/` | checkpoints and their `.eval.json` reports |

Every console episode is replayable from the picker in the status strip, see [Replay](console/replay.md).

## Next

- [Rules and zones](console/rules-and-zones.md) to type your own rules.
- [Command line](cli.md) for every flag.
- [Concepts](concepts.md) if any of the words above were new.
