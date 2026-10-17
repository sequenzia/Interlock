# Replay

Every episode the server runs is written as one JSONL file under `backend/logs/runs/`. The console can stream any of those files back through the same messages it uses for a live episode. Nothing is recomputed and Jev is never called.

## Starting a replay

The replay picker in the status strip lists the logged runs, newest first, by run id: a timestamp, the seed and whether the shield was on, for example `2026-10-17T01-27-46_seed0_on`. Pick one. The source badge turns amber and reads `replay`, the step counter shows `0 / N` where N is the number of records, and the rules panel switches to the rules as they were at the start of that run.

The list is read when the console connects and after a reset. A run that just finished appears after you press "reset" or refresh the page.

## What works

| Control | In replay |
| --- | --- |
| "play", "pause", "step", speed | work as in live; each step emits the next record |
| Decisions strip, inspector, scrubbing | work, since they only read records |
| Road view | shows the logged vehicles and zones |
| step / jev / cost / violations stats | recomputed from the records played so far |
| "shield on" toggle | disabled |
| Rules, presets, zones, thresholds | read-only; the panel follows each record's rule list |
| Approval queue | shows nothing; escalations in the log are already resolved and appear in the inspector with the operator's answer |
| seed and "reset" | start a new live episode on that seed |

The metrics message in replay (decision counts, violations, human answers, cost) is recomputed from the records rather than carried over, so the numbers are exactly those of the logged run up to the current step.

## Back to live

"back to live" ends the replay and starts a fresh live episode on the seed the session had before. Reset does the same with the seed you typed.

## Uses

- **An offline backup.** With the server in mock mode and no network, a logged live run replays with every probability, latency and request intact.
- **A review.** Walk a run step by step in the inspector to see where the shield intervened and what the operator answered.
- **Headless runs too.** `interlock run` writes to the same folder, so a CLI episode, including one with `--zone-at-step`, is replayable in the console.

Evaluation runs land under `backend/logs/eval/` instead and do not appear in the picker.
