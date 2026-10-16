# Shielded RL with Jev: Project Brief

Oct 16, 2026

Build a small app where Jev, a decision model, acts as a runtime safety shield
for a reward-only RL driving agent, with low-confidence calls escalated to a
human operator. It is a demo for a short talk on runtime safety for learned
policies and on human-on-the-loop design. The schedule, module contracts and
decisions live in `build-plan.md` next to this file.

## Purpose and goals

The project combines a long-standing interest in reinforcement learning with a
current interest in decision models such as Jev. Two questions drive it: can a
policy trained once on task reward be made to follow rules written later in
plain English, and can the system tell when it should ask a person?

Goals for the demo:

1. Show a reward-only RL policy being made safe at runtime, with rules typed in plain English and no retraining.
2. Show a clean human-on-the-loop design: the system knows when to ask a person.
3. Show strong frontend and inspection-UI craft: an operator console plus a decision inspector.
4. Back it with honest numbers: violations, task return, latency, cost and calibration.
5. Even if unfinished, learn a lot and have a clear story about design decisions.

The one-line pitch: *the policy was trained once; the rules changed live, in plain English.*

## The concept

The idea combines two of five brainstormed options: Jev as a **safety shield** and **confidence-based escalation** to a human.

- **Shield.** In safe RL, a shield is a runtime monitor that vetoes unsafe actions before they execute. The RL agent proposes an action; Jev judges it against operator constraints and returns a decision with a probability. Code then allows it, blocks it (falling back to the agent's next-best action), or escalates.
- **Escalation.** When Jev's answer sits in an uncertain band, the sim pauses and the decision goes to an operator approval queue. This is the human-on-the-loop question: when should autonomy ask a person?
- **Key design choice.** The agent is trained on task reward only and knows nothing about the rules. Constraints are added at runtime, in plain English, with no retraining.

Options considered and not chosen (useful as a backup slide):

| Option | Why not chosen |
| --- | --- |
| Jev as a natural-language reward model | Agent must retrain whenever intent changes; weak live demo |
| Jev as high-level behavior selector over RL controllers | Good System 1 / System 2 story, but more moving parts |
| Jev as a zero-shot policy vs a trained agent | Fun, but leans on Jev's known weak spots |

## Why Jev fits

Jev picks from options you define and returns calibrated probabilities, which is exactly what a shield needs.

**What it is**

- A non-generative "System One" decision model from TypeSafe AI, released in early access on Sept 15, 2026 ([freeapihub](https://freeapihub.com/blog/jev-ai-model), [Lindy](https://www.lindy.ai/blog/jev-ai)).
- Returns a typed decision plus probability instead of text. Because the developer defines the possible outputs, it cannot invent a category or return malformed JSON ([YourStory](https://yourstory.com/ai-story/what-is-jev-typesafe-ai-decision-model)).
- Trained with a method TypeSafe calls Reinforcement Learning for Calibrated Decisions (RLCD) ([Lindy](https://www.lindy.ai/blog/jev-ai)). Good hook for an RL audience.
- Evaluates multiple questions independently and in parallel in one request; if a later decision depends on an earlier one, your code sequences it ([Builder.io](https://www.builder.io/blog/what-is-jev)).
- Available via TypeSafe's API, OpenRouter and Vercel AI Gateway, with a LangChain integration ([freeapihub](https://freeapihub.com/blog/jev-ai-model)).

**Evidence it fits**

- Vercel replaced an OpenAI model with Jev on a classifier that reviews commands for safety and saw 5 to 18 times faster results with better accuracy ([Lindy](https://www.lindy.ai/blog/jev-ai)).
- TypeSafe demoed Jev playing Doom at 10 calls per second ([LinkedIn post](https://ch.linkedin.com/in/sapbanking)), so real-time step rates are plausible.

**Known weaknesses (design around these)**

- TypeSafe's docs list arithmetic, counting and multi-hop instructions as weaknesses; a benchmark found Jev matches general LLMs on knowledge-driven decisions but not on multi-step calculation ([arXiv 2610.11978](https://arxiv.org/pdf/2610.11978)).
- Consequence: **never ask Jev to do geometry.** Code computes distances, gaps, closing speeds and lane facts; Jev makes the judgment call on pre-digested facts.

The request and response schema, the three question types and pricing were confirmed from TypeSafe's own docs and are recorded in `build-plan.md`, section 2.

## Environment choice: HighwayEnv

Use [HighwayEnv](https://highway-env.farama.org/quickstart/) (`highway-fast-v0`) with the official Stable-Baselines3 DQN recipe. There is no need to build the agent or the environment; the shield is the standout work.

**Why it fits**

- **Reward knows nothing about rules.** Reward = high speed + no collisions + a small right-lane bonus. No speed limits, following distance or lane closures, so a speed-hungry agent will break rules added later.
- **Discrete, readable actions.** Default `DiscreteMetaAction`: LANE_LEFT, IDLE, LANE_RIGHT, FASTER, SLOWER. A human and Jev can both judge these.
- **Ranked fallbacks for free.** DQN gives a Q-value per action, so the next-best action is already computed when the top one is blocked.
- **Semantic state.** The simulator exposes nearby vehicles' positions and velocities, so turning state into plain facts is straightforward.
- **Comfortable pacing.** Default `policy_frequency` is 1 decision per second of sim time, so API latency is not a problem.
- **Fast to train.** The docs' DQN example (MLP `[256, 256]`, lr 5e-4, buffer 15000, gamma 0.8, `learn(2e4)`) takes about 25 minutes on a laptop.
- **Prior art to contrast.** [ceriad](https://github.com/oliverc1623/ceriad) used GPT-3.5 as a planner over a DQN actor in highway-env. Talking point: chat LLM vs decision model on latency and cost.

**Tradeoff to own in the talk:** it is cars, not aircraft or robots. The shield is domain-agnostic; HighwayEnv was the fastest route to a reward-only policy that misbehaves in readable ways.

**Alternatives considered**

| Option | Verdict | Reason |
| --- | --- | --- |
| [PyFlyt](https://pypi.org/project/pyflyt/) (quadrotor and fixed-wing UAV envs) | Pass; mention as "next step" | Most ambitious, but continuous low-level control, no pretrained agents; shielding at control-loop rate is the wrong job for Jev |
| [AI Safety Gridworlds](https://arxiv.org/pdf/1711.09883) / [safe-grid-gym](https://github.com/jvmancuso/safe-grid-gym) | Pass | Conceptually perfect (hidden safety performance function separate from reward), but old pycolab stack and dependency risk |
| [Safety-Gymnasium](https://safety-gymnasium.readthedocs.io/) | Pass | Continuous MuJoCo control with costs built in; same mismatch as PyFlyt |
| [RL Baselines3 Zoo](https://huggingface.co/sb3) pretrained agents (200+) | Pass | Truly zero training, but pixel-based Atari and other agents don't misbehave against readable rules |
| Existing pixel-based Atari agents ([atari-rl](https://github.com/sequenzia/atari-rl)) | Pass | Semantic facts would need [OCAtari](https://oc-atari.readthedocs.io/en/stable/) RAM extraction, Atari rules feel arbitrary as operator constraints, and the 2023-era gym stack risks version friction. Stretch only: run the same shield on Seaquest to show it is domain-agnostic |

## Architecture

A Python backend runs the sim, policy and shield, and streams each step to a React/TypeScript frontend that renders the scene itself. The built-in highway-env renderer is not used in the demo UI.

| Component | Tech | Responsibility |
| --- | --- | --- |
| Environment | `highway-env`, Gymnasium | `highway-fast-v0`, Kinematics obs, DiscreteMetaAction |
| Policy | Stable-Baselines3 DQN | Trained on task reward only; exposes Q-values for all 5 actions |
| Fact extractor | Python | Turns state + each candidate action into structured facts with units |
| Constraint store | Python | Operator constraints as plain-English strings, editable at runtime |
| Jev client | Python, TypeSafe API | Batched per-step checks; **mock mode** replays logged responses offline |
| Shield | Python | Allow / fallback / escalate logic, thresholds, next-best search |
| Decision log | JSONL | Every step: state, candidates, facts, Jev output, outcome, human override |
| Server | FastAPI | Sim loop control; streams steps over WebSocket; receives operator actions |
| Frontend | React + TypeScript, Canvas | Road view, constraint panel, approval queue, decision inspector, metrics |
| Eval harness | Python | Headless batch runs with and without shield; metrics + calibration |

The repo layout and module contracts are in `build-plan.md`, section 4.

## Shield design

Each step makes one batched Jev request covering every candidate action against every active constraint, then code decides allow, fallback or escalate. This is the standout part of the project.

All five actions are checked against every rule in one batched request, so falling back costs no extra round trip; every step is logged and streamed to the UI.

**Per-step loop**

1. The DQN ranks all 5 actions by Q-value.
2. The fact extractor turns state + each candidate into facts, computed in code.
3. One batched Jev request asks, per (action, constraint) pair: does this action violate this constraint? One question per pair means the UI can say which rule fired.
4. For the top-ranked action, combine results into a violation probability (the max across constraints).
5. Decide:
   - Confident safe (below `T_ALLOW`): execute.
   - Confident violation (above `T_BLOCK`): move to the next-best action that is confidently safe; answers are already in hand, so no extra round trip.
   - In between: pause the sim and send to the operator queue.
   - Every action blocked: default to SLOWER (or IDLE), and flag it in the log.
6. Log everything and stream the step to the UI.

Starting thresholds: `T_ALLOW = 0.2`, `T_BLOCK = 0.8`. Tune these during eval and show the tradeoff curve.

**Fact extraction (the key engineering choice)**

Jev is weak at arithmetic and multi-hop reasoning, so code does the geometry and Jev judges. Example facts for action LANE_LEFT, shown here as sentences (Jev receives the same facts as structured JSON):

- "Ego speed: 31 m/s. Ego lane: 2 of 4 (lanes numbered from the left)."
- "Action LANE_LEFT moves ego into lane 1."
- "Nearest vehicle in lane 1: 8 m behind, closing at 4 m/s. Next vehicle ahead in lane 1: 42 m."
- "Lane 1 is closed starting 120 m ahead (operator zone)."

Prefer plain numbers with units over raw normalized observation values.

**Escalation**

- The sim pauses; the queue shows the action, facts, the rule in question and Jev's probability.
- Operator approves or denies. Deny uses the next-best confident-safe action.
- Every human decision is logged as a labeled example (future use: threshold tuning or shield fine-tuning).
- Optional timeout for unattended runs: default to deny.

**Reliability**

- **Mock mode:** a Jev client that replays logged responses, so the demo runs with no network.
- Cache identical (facts, constraint) questions.
- When the judge is unreachable and the answer is not cached, escalate to the human and say so. Never substitute a fake judgment.
- Record a backup video of the live demo; never rely on a live API call in the room.

The full log record schema is in `build-plan.md`, section 7.

## Demo constraints

The operator types these live; each one also has a rule-based checker used only for scoring, never for the shield's decision.

| Constraint (as typed) | Why the agent breaks it | Ground-truth checker |
| --- | --- | --- |
| "Speed limit 25 m/s" | Reward pays for 20 to 30 m/s, so it pushes the top | Ego speed after action > 25 |
| "No lane change if a vehicle is within 10 m in the target lane" | Agent weaves aggressively for speed | Gap in target lane < 10 m |
| "Keep the left lane for passing only" | Agent will cruise in any fast lane | In leftmost lane with no slower vehicle ahead within N m |
| "Lane 3 is closed ahead for a work zone" (added mid-episode) | Agent has never seen a closure | Ego in or entering lane 3 within the zone |

The work-zone constraint is the showstopper: drop it in mid-episode and the agent visibly changes behavior with no retraining. A closed zone needs a matching overlay in the road view. Jev's real value is constraints that are fuzzy or written on the fly; the checkers exist only so violations and calibration can be measured.

## Evaluation and metrics

Run the same seeded episodes with and without the shield and report five numbers; the before/after violation rate is the must-have.

| Metric | How measured |
| --- | --- |
| Constraint violations per episode | Ground-truth checkers, shield off vs on |
| Task return and collisions | Env reward and crash count, shield off vs on (the cost of safety) |
| Escalation rate | Share of steps sent to the operator, per threshold setting |
| Jev latency and cost | p50 / p95 ms per batched request; cost per episode |
| Calibration | Reliability plot: bin Jev's p(violation), compare to ground-truth rate; a few hundred labeled decisions is enough |

Also sweep `T_ALLOW` and `T_BLOCK` to plot violations against escalation rate. That tradeoff curve is the slide for "how I chose the threshold." For the human escalations in eval runs, use the ground-truth checker as a simulated operator.

## UI

The UI carries the demo: a C2-style operator console plus an inspection view for the AI's decisions.

| View | Shows | Priority |
| --- | --- | --- |
| Road view (Canvas) | Ego and nearby vehicles from streamed positions; closed-zone overlays; blocked action drawn as a ghost arrow | Must |
| Constraint panel | Text box to add, toggle and remove plain-English rules live | Must |
| Status strip | Shield on/off, current decision (allowed / fallback / escalated), latency | Must |
| Approval queue | Paused decision with facts, rule, probability; Approve / Deny | Must |
| Decision inspector timeline | One tick per step, colored by outcome; click to see the exact Jev questions, answers and Q-values | Nice |
| Metrics panel | Before/after violations, escalation rate, calibration plot | Nice |

Shield on/off should be a single toggle on the same seeded episode, so the audience sees the difference side by side.

## Scope cut lines

If time runs short, a clean headless shield plus a good log viewer is still a strong talk.

- **Must have:** trained agent, working shield with fallback, road view, constraint panel, approval queue, decision log, one before/after metric, mock mode, backup video.
- **Nice to have:** decision inspector timeline, calibration plot, threshold sweep, in-UI metrics panel.
- **Stretch:** multiple scenarios (merge, roundabout), click-to-place zones, WebGL road view, comparison against a chat-LLM shield on latency and cost.

## Presentation talking points

The talk should be about design decisions at the boundary between learned policy, deterministic code, decision model and human.

1. **The pitch:** trained once, rules changed live in plain English.
2. **Why code computes the facts:** Jev's documented weakness at arithmetic and multi-hop reasoning; the boundary between code and model is a design choice, not an accident.
3. **Choosing the escalation threshold:** show the violations vs escalation-rate curve.
4. **Calibration matters:** probability is only useful for escalation if 80% means right about 80% of the time; show the reliability plot.
5. **Humans as a data source:** approve/deny clicks become labeled data for tuning thresholds or the shield.
6. **Decision model vs chat LLM:** latency, cost and typed outputs, contrasted with prior work that used GPT-3.5 as a planner in highway-env.
7. **Honest scoping:** why driving instead of aircraft, and why PyFlyt is the natural next step.

## Risks and open questions

The biggest risk was the Jev integration details, so they were confirmed first.

| Risk | Mitigation |
| --- | --- |
| Jev misjudges plain numeric comparisons | Probe on Day 1; fallback is regex-extracted comparison facts computed in code |
| Jev latency too high for smooth playback | Sim runs at 1 decision/s; slow playback further; cache repeats |
| Network or API failure during the talk | Mock mode replaying logged responses; judge-unavailable escalation; backup video |
| Agent too cautious to break rules | Raise `reward_speed_range` or vehicle density; pick seeds where violations happen |
| Jev misjudges facts | Simplify facts further; one constraint per question; report misses honestly |
| UI scope creep | Cut lines above; headless shield first |

**Open questions**

- [ ] Presentation date and length?
- [ ] Is a live demo expected, or are slides plus a recorded demo fine?

## Notes for Claude Code sessions

Treat this brief and `build-plan.md` as the project's source of truth; keep the shield headless until it works.

- **Do not guess the Jev API.** The confirmed schema is in `build-plan.md`; re-verify with a real request before writing `jev_client.py`.
- **Keep geometry in code.** Facts passed to Jev are pre-computed, structured, with units.
- **Build mock mode early** so all UI and eval work runs without network or API cost.
- **Log first, visualize second.** The JSONL log is the contract between backend, UI and eval.
- **Pin versions** (`highway-env`, `gymnasium`, `stable-baselines3`) once training works.
- **Frontend:** Vite + React + TypeScript; draw the road on Canvas from streamed state, not from highway-env's renderer.
- **Writing style:** avoid em dashes in docs, slides and UI copy.

## Sources

- [HighwayEnv: Getting Started](https://highway-env.farama.org/quickstart/)
- [TypeSafe API reference](https://docs.typesafe.ai/api)
- [TypeSafe quickstart](https://docs.typesafe.ai/introduction/quickstart)
- [Jev AI model overview (freeapihub)](https://freeapihub.com/blog/jev-ai-model)
- [What Is Jev AI? (Lindy)](https://www.lindy.ai/blog/jev-ai)
- [Introducing Jev (YourStory)](https://yourstory.com/ai-story/what-is-jev-typesafe-ai-decision-model)
- [What is Jev and how to use it (Builder.io)](https://www.builder.io/blog/what-is-jev)
- [Specialized Decision Models vs. General-Purpose LLMs: Benchmarking Jev (arXiv 2610.11978)](https://arxiv.org/pdf/2610.11978)
- [Jev cost and Doom demo (LinkedIn post)](https://ch.linkedin.com/in/sapbanking)
- [ceriad: Planner-Actor-Reporter in highway-env](https://github.com/oliverc1623/ceriad)
- [PyFlyt](https://pypi.org/project/pyflyt/)
- [AI Safety Gridworlds (arXiv 1711.09883)](https://arxiv.org/pdf/1711.09883)
- [safe-grid-gym](https://github.com/jvmancuso/safe-grid-gym)
- [Safety-Gymnasium](https://safety-gymnasium.readthedocs.io/)
- [RL Baselines3 Zoo on Hugging Face](https://huggingface.co/sb3)
- [OCAtari](https://oc-atari.readthedocs.io/en/stable/)
- [atari-rl](https://github.com/sequenzia/atari-rl)
