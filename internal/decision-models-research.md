# Jev and Decision Models: Research Notes

Written Oct 16, 2026 from public sources, while choosing a name for this
project. Everything here is what vendors, press and bloggers say, except where
a line points at `jev-spike-results.md`, `eval/latest.json` or
`build-plan.md`, which hold what this project measured or confirmed against
the API. The category is five weeks old and moving fast, so re-check any
vendor claim before quoting it in the talk.

## 1. What a decision model is

- TypeSafe coined the term "System One model" when it released Jev on
  Sept 15, 2026. The press settled on "decision model" for the category, and
  TypeSafe's own docs never use that phrase.
- The contract: send state plus typed questions, get typed answers with
  probabilities. TypeSafe's one-line version is "unstructured state in, typed
  probabilistic decisions out." No text generation, no parsing.
- The contrast with an LLM: an LLM generates a string that your code must
  parse and trust. A decision model scores a closed answer space that the
  developer defined, so it cannot invent a category or return malformed
  output. TypeSafe's phrases for this are "decisions, not strings", "smart
  if-statements", "fuzzy decision rules" and "more like code".
- Calibration is the point. A probability is only useful for thresholding if
  0.8 means roughly eighty percent. TypeSafe's docs also warn that the
  `confidence` field is distribution concentration, not measured accuracy, so
  thresholds should come from labeled data. That warning is why this project
  has an eval harness and a reliability diagram.
- Positioning across the press: a complement to LLMs, not a replacement. Good
  fits are closed answer spaces, high call volume, and decisions that software
  acts on directly. Poor fits are anything that needs generation, arithmetic,
  counting or multi-hop reasoning.

## 2. Jev, the facts

**Vendor.** TypeSafe AI, San Francisco, founded 2024. The public face is Diogo
Almeida, a former OpenAI researcher who worked on RLHF. Co-founders are Erik
Gafni and Sasha Sheng. Homepage tagline: "AI lab building machine-native
intelligence infrastructure for automation, designed to make decisions within
software."

**Timeline.** Early access on Sept 15, 2026. The API reported `jev-1.13.0` on
Oct 16 and that version is pinned in `backend/jev_client.py`. Press reported
Jev 1.14 behind the `jev-preview` alias on Oct 14 with experimental image
input, a Box type and a 262k-token context. This project uses 1.13.0 and none
of the 1.14 features.

**API shape.** `POST /v1/systemone` with a `state` and a map of `questions`.
Section 2 of `build-plan.md` holds the full contract as read from the docs.
Three question types:

| Type | Asks | Returns |
| --- | --- | --- |
| `noul` | Is this statement true? | `noul`, a number from 0 to 1 |
| `choice` | Pick one option from this list | `choice`, `probabilities`, `confidence` |
| `score` | Rate against this ordered rubric | `score`, `legend`, `probabilities`, `confidence` |

The shield uses only `noul`: one question per (candidate action, rule) pair,
phrased as a positive assertion with the rule text verbatim. No public source
explains the word "noul".

**Price and speed.** $0.042 per million input tokens, output tokens free. The
vendor quotes roughly 100 ms typical latency with a 70 to 500 ms range.
Measured here, a full step of five candidates at request shape B is p50 157 ms
and p95 247 ms, a 60-step episode costs about $0.011, and the standard
deviation over five repeats of an identical request is at most 0.05. Those
numbers live in `jev-spike-results.md`.

**Limits.** 64k tokens per request, 32k per question, 80 requests per second,
32 MiB body.

**Training.** TypeSafe calls its method Reinforcement Learning for Calibrated
Decisions, RLCD. The stated goal is that predicted probabilities match
real-world outcome frequencies rather than human preference, which is the
opposite objective from RLHF. There is no paper or technical report, so the
loss, reward model and procedure are undisclosed. The homepage also claims "a
new architecture and a new sampler" without detail. Treat RLCD as a
proprietary label for an undisclosed method, not a standardized technique.

**Documented weaknesses.** TypeSafe's docs list arithmetic, counting, numeric
comparison, multi-hop questions, literal reading of negation, and accuracy
loss from irrelevant state. An independent benchmark (arXiv 2610.11978) found
Jev matches general LLMs on knowledge-driven decisions but not on multi-step
calculation. Our spike confirmed the numeric-comparison and negation misses.
This is the reason geometry stays in code and questions are positive
assertions.

**Distribution.** TypeSafe's API, OpenRouter, Vercel AI Gateway, a LangChain
integration and a promptfoo provider.

**Vendor and press claims, quote only with attribution.**

- "193.6x faster, 444.6x cheaper" than LLMs, on TypeSafe's own System One
  workflows.
- A Jack & Jill case study on candidate screening: 88% cost reduction and 2x
  speed.
- Vercel swapped an OpenAI model for Jev in a command-safety classifier and
  saw 5 to 18x faster results with better accuracy (Lindy).
- TypeSafe demoed Jev playing Doom at ten calls per second.
- Funding: TechCrunch reported a $7.5B valuation on Oct 9. An $870M Series A
  led by a16z was reported by a single outlet. Leave the round out of the
  talk.

## 3. Where the names come from

**Jev is William Stanley Jevons.** TypeSafe's FAQ says it directly: "We named
Jev after William Stanley Jevons." The reference is the Jevons paradox: when
steam engines burned coal more efficiently, Britain used more coal, because
cheap power found new uses. TypeSafe's version: "Every order of magnitude
drop in the cost of intelligence unlocks orders of magnitude more use cases."
This project is a small instance of the paradox. Because a judgment costs a
fraction of a cent, the shield makes one batched request per step and checks
every candidate action against every active rule.

**Jevons also built a machine that does this shield's job.** In 1869 he built
the Logic Piano, a device shaped like a small upright piano. Pressing keys
enters the premises of a logical argument, and the machine mechanically
eliminates every combination of terms inconsistent with them. Whatever remains
is the conclusion. He presented it to the Royal Society in 1870 under the
title "On the Mechanical Performance of Logical Inference", and it survives at
Oxford's History of Science Museum. Swap premises for operator rules and
combinations for candidate actions and you have the shield: elimination
against constraints, not generation.

**System One is Kahneman.** The term comes from "Thinking, Fast and Slow":
System 1 is fast, automatic, intuitive judgment; System 2 is slow, effortful,
deliberate reasoning. Kahneman describes System 2 as the monitor that mostly
endorses what System 1 suggests and occasionally overrides it, and he has
said in interviews that the monitoring is lax. One reviewer compressed the
book to "System 1 proposes, System 2 disposes." TypeSafe uses the term for the
fast half only. Nothing in their launch post or docs describes humans, review
or escalation in Jev's loop. The console in this project is the System 2
half: the uncertain band is where the fast judgment hands off to a slow one.

## 4. The landscape, mid-October 2026

Compiled from GoSearch's roundup of the Forbes guide to decision models.
Not independently verified; use it to show the category exists, not to compare
products.

| Model | Vendor | Notes |
| --- | --- | --- |
| Jev | TypeSafe | First to market; hosted API; choice, score, yes/no |
| Decisions API | OpenAI | Yes/no, multiple-choice, numeric scoring over text and images; one source says DevDay preview, another says public beta on Oct 7 |
| Microsoft-Decision-1 | Microsoft | Classification, routing, verification via Foundry and OpenRouter |
| Clef, Clef Flash, Clef-omni | Cloudflare | Edge and low-latency routing; omni is multimodal |
| Pplx-Decider V1.1 27B | Perplexity | Hosted or open weights, multimodal |
| D1, D1-3B, D1-Omni-600M | Liquid AI | Hosted plus small open-weight local models |
| Mercury Decide | Inception | Via OpenRouter, free rate-limited tier |
| Solar Decide, Solar Decide Flash | Upstage | Long-input classification and routing |
| Strands Decider 2B | Strands Agents | Open source, on Bedrock; reportedly removed the language-model head |
| Span-01 | Respan | Agent monitoring: unsafe actions, frustration, escalation |
| Laya | Convai Innovations | Lightweight open weights, multilingual |
| Drex | Nace.AI | Several questions in one pass, compliance work |
| Kev, SemIf (formerly OpenJev), Verdict, Von | Independent | Open-source reimplementations and adapters |
| Jevman | Opper AI | Game-based benchmark for rapid decisions |

Two patterns worth noting. First, the shared vocabulary across vendors is
calibrated, typed, threshold, escalate and review. Second, models get short
abstract names (Jev, Clef, Dots, Laya, Drex, Span). A system built around a
model should not look like another model, which shaped the naming decision in
section 7.

**An independent, skeptical benchmark.** Red Hat (Oct 2, 2026) ran Jev 1.13.0,
Laya and DiffusionGemma against pre-trained classifiers (deberta-v3 for prompt
injection, granite-guardian for content safety) and LLM judges (Qwen3.6-35B
and others) on class-balanced prompt-injection and content-safety sets through
NeMo Guardrails. Jev led content safety at 86.20% accuracy with a 360 ms
median, and trailed on prompt injection at 86.35% against deberta's 89.01% at
54 ms. The authors' conclusion: "we did not find that decision models produced
faster, cheaper, or higher-quality answers compared with LLM-as-a-judge", and
pre-trained classifiers "remain extremely competitive" for well-defined risks
with plenty of training data.

The takeaway for the talk: do not pitch Jev as a better classifier. Pitch what
this project actually uses it for. The rules are typed by an operator at
runtime, so there is no training set to fit a classifier to. Each rule is
judged per candidate action, and the probability is calibrated well enough to
split allow, fall back and ask. The eval measures that last claim rather than
assuming it.

## 5. What this project measured

Pointers only; the numbers live in the files named.

- `jev-spike-results.md`: 172 requests. One of 43 labeled fact sets on the
  wrong side of 0.5. Numeric comparison misses, so comparison facts are
  precomputed in code. Negation as typed misses, positive rephrase does not.
  JSON state and prose state differ by 0.04 mean absolute. Repeat std at most
  0.049. Step p50 157 ms, p95 247 ms.
- `eval/latest.json` and section 10 of `build-plan.md`: violations per
  episode fall from 58.1 with the shield off to 2.65 at thresholds 0.2 / 0.8.
  Over 93,285 labeled checks the expected calibration error is 0.093 and
  accuracy at a 0.5 cut is 97.5%, with the speed rule near perfect and the
  passing rule weakest. `backend/metrics.py` computes both ECE and the Brier
  score per rule, plotted as a reliability diagram in `plots/calibration.png`.
- The passing rule sits near 0.5 regardless of phrasing. That is the
  human-on-the-loop moment the design wants, not a defect to prompt away.

## 6. Talk hooks

- Jev is named for Jevons, who in 1869 built a machine that eliminated every
  option inconsistent with your premises. That is what Jev does to the agent's
  candidate actions here, at about 160 ms a step.
- TypeSafe calls Jev a System One model. Kahneman's System 2 is the slow
  monitor that overrides when something looks off. This console is the
  System 2 that Jev's own docs never mention.
- Jevons' paradox, applied: once a judgment costs a fraction of a cent, you
  make it for every action, every step, against every rule.

## 7. Naming decision

The project is **Interlock**. A safety interlock permits an action only when a
condition holds, with a supervised override for an authorized person. That is
allow, fall back and escalate in one word, and it is vocabulary that aviation,
rail and industrial safety engineers already use. MIT CSAIL and Toyota
published "A Safety Interlock for Self-driving Cars", a small trusted
component that oversees the rest of the system and forces a safe mode, which
is prior art for the term in exactly this role. No company owns the name in
this space.

"Shield" stays as the lowercase technical term for the mechanism, because
shielding is the established name for runtime action blocking in safe RL
(Alshiekh et al., 2018) and it lives in the log contract and CLI flags. It is
no longer used as a product name in the header, page title or package names.

Names considered and set aside: Upright (Jevons' Logic Piano; the connection
needs a two-hop explanation), System Two (strongest talk line, but reads as a
riff on TypeSafe's branding), Brier (the calibration metric; most product-like,
least self-explanatory), Slow Lane, Second Thought, Deadband, Veto, Marshal,
Flagger (collides with the CNCF tool), Checkride (collides with Check-Ride.ai,
launched Sept 2026).

## Sources

- TypeSafe, "Introducing System One Models & Jev":
  https://typesafe.ai/blog/introducing-system-one-models-and-jev
- TypeSafe docs: https://docs.typesafe.ai
- TypeSafe homepage: https://typesafe.ai
- DataCamp, "Jev: TypeSafe's System One Model Explained":
  https://www.datacamp.com/blog/system-one-models-jev
- Olostep, "What Is Jev AI?": https://www.olostep.com/blog/jev-ai
- Turing Post, "What Is Jev AI? Inside TypeSafe's RLCD Model":
  https://www.turingpost.com/p/what-is-jev-rlcd
- MarkTechPost, Jev 1.14 release:
  https://www.marktechpost.com/2026/10/14/typesafe-ai-jev-1-14-images-box-long-context/
- TechCrunch, valuation report:
  https://techcrunch.com/2026/10/09/the-maker-of-non-text-ai-model-jev-valued-at-7-5b-just-weeks-after-launch/
- Fortune, "Jev, an AI for making quick decisions, has been a viral hit":
  https://fortune.com/2026/10/08/jev-an-ai-for-making-quick-decisions-has-been-a-viral-hit-in-silicon-valley-but-openai-is-hot-on-its-heels/
- Forbes, "Decisions, Decisions: A Guide To The New Wave Of AI Decision Models":
  https://www.forbes.com/sites/ronschmelzer/2026/10/12/decisions-decisions-a-guide-to-the-new-wave-of-ai-decision-models-besides-jev/
- GoSearch, "AI Decision Models in 2026":
  https://www.gosearch.ai/blog/ai-decision-models-in-2026/
- Red Hat Developer, "Benchmarking AI decision models against traditional guardrails":
  https://developers.redhat.com/articles/2026/10/02/benchmarking-ai-decision-models-against-traditional-guardrails
- arXiv 2610.11978, decision model benchmark: https://arxiv.org/pdf/2610.11978
- IEEE Computer Society, W. Stanley Jevons: https://history.computer.org/pioneers/jevons.html
- Jevons, "On the Mechanical Performance of Logical Inference" (1870):
  https://thesciencebookstore.com/books/2019/11/jevons-logical-machine-1870.html
- Kahneman interview, PNAS: https://pmc.ncbi.nlm.nih.gov/articles/PMC3752209/
- MIT CSAIL / Toyota, "A Safety Interlock for Self-driving Cars":
  https://toyota.csail.mit.edu/node/65
- Alshiekh et al., "Safe Reinforcement Learning via Shielding" (AAAI 2018):
  https://arxiv.org/abs/1708.08611
