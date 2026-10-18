# Training and policy

Three small modules give the shield something to judge: `backend/env.py` builds the simulator, `backend/train.py` trains and scores a Stable-Baselines3 DQN, and `backend/policy.py` wraps a checkpoint so every step yields all five actions ranked by Q-value. The policy is trained on task reward alone and never sees an operator rule. That separation is the premise of the whole project.

## The reward function

The reward is the highway-env default for `highway-fast-v0`, untouched by Interlock: `DEFAULT_CONFIG` overrides the road and the traffic, never a reward term. Every step the environment computes four per-step values, weights three of them, normalizes the sum and multiplies by the fourth.

| Term | Weight | Per-step value | Contribution |
| --- | --- | --- | --- |
| Collision | `collision_reward` = -1 | 1 if the ego crashed on this step, else 0 | -1 or 0 |
| High speed | `high_speed_reward` = 0.4 | Forward speed mapped linearly from `reward_speed_range` 20 to 30 m/s onto 0 to 1 and clipped, so 20 m/s or slower earns 0 and 30 m/s or faster earns the full weight. Forward speed is speed times the cosine of the heading, so a car mid lane change earns slightly less | 0 to 0.4 |
| Right lane | `right_lane_reward` = 0.1 | Lane index from the left divided by the lane count minus one. In the four-lane demo and Interlock's numbering, lane 1 earns 0, lane 2 a third, lane 3 two thirds, lane 4 the full weight. During a lane change the target lane counts | 0 to 0.1 |
| Lane change | `lane_change_reward` = 0 | Each lane change action | 0, so no term |
| On road | multiplier | 1 while the ego is on the road, which it always is on this highway | times 1 |

`normalize_reward` is true, so the weighted sum, which lies between -1 and 0.5, is mapped linearly onto 0 to 1:

```
reward = (collision + speed + lane + 1) / 1.5
```

That mapping is why the `reward` in a log record and the `r=` figure in the console's step header read 0.8 to 1.0 on an ordinary step. A step without a crash scores between 0.667 and 1.0; a crash scores between 0 and 0.333.

| Situation | Weighted sum | Reward |
| --- | --- | --- |
| Lane 1 at 20 m/s or slower, no crash | 0.0 | 0.667 |
| Lane 4 at 20 m/s, no crash | 0.1 | 0.733 |
| Lane 4 at 25 m/s, no crash | 0.3 | 0.867 |
| Lane 1 at 30 m/s, no crash | 0.4 | 0.933 |
| Lane 4 at 30 m/s or faster, no crash | 0.5 | 1.000 |
| Lane 4 at 30 m/s, crash | -0.5 | 0.333 |
| Lane 1 at 20 m/s, crash | -1.0 | 0.000 |

An episode terminates on a crash and truncates after `duration` steps, 60 here, so the maximum task return is 60. The one-step collision penalty is the smaller part of the cost of crashing: the larger part is every remaining step's reward of at least 0.667 that the agent no longer collects. With `gamma` 0.8 the Q-values weigh about five steps ahead, which is why the trained policy avoids the collisions it can see coming and still runs at the top of the speed band.

Nothing in these terms mentions a speed limit, a following gap, a passing lane, a closed lane or a lane-change count. The speed term pays most at 30 m/s, so a rule such as "Speed limit 25 m/s" sits inside the band the policy was trained to climb, and that rule is the one it breaks most with the shield off; the [evaluation page](../../user-guide/evaluation.md) has the counts. The per-step `reward` lands in the [log record](../contracts/log-record.md) rounded to four places, and the evaluation sums it per episode as task return.

The source is `HighwayEnv._reward` and `HighwayEnv._rewards` in highway-env 1.12; the fast variant changes the traffic and the simulation frequency, not the reward. The [highway-env rewards page](https://highway-env.farama.org/rewards/) describes the same terms.

## `backend/env.py`

```python
ENV_ID = "highway-fast-v0"
ACTION_NAMES = ("LANE_LEFT", "IDLE", "LANE_RIGHT", "FASTER", "SLOWER")
ACTION_INDEX = {"LANE_LEFT": 0, "IDLE": 1, "LANE_RIGHT": 2, "FASTER": 3, "SLOWER": 4}
DEFAULT_CONFIG = {"lanes_count": 4, "duration": 60, "vehicles_count": 30, "policy_frequency": 1}
```

`ACTION_NAMES` is derived at import from `DiscreteMetaAction.ACTIONS_ALL`, sorted by index, so the names can never drift from highway-env's own action order. `tests/test_env.py` pins the tuple and `ACTION_INDEX["SLOWER"] == 4`.

`make_env(config=None, render_mode=None)` merges `DEFAULT_CONFIG` with any overrides and calls `gym.make`. It never seeds. Callers seed on reset (`env.reset(seed=seed)`), which keeps every episode in an eval run seeded explicitly and visibly. A seeded reset is reproducible across two environments.

| Setting | Value | Why |
| --- | --- | --- |
| `lanes_count` | 4 | Room for a lane 3 work zone with lanes on both sides |
| `duration` | 60 | Steps per episode; leaves time for a mid-episode zone drop |
| `vehicles_count` | 30 | Enough traffic that gaps and passing matter |
| `policy_frequency` | 1 | One decision per simulated second, so a Jev round trip fits comfortably |

The reward is not in `DEFAULT_CONFIG` because it is not overridden; [the reward function](#the-reward-function) above spells out the default the policy trains on.

## `backend/train.py`

### `build_model(env, seed) -> DQN`

The hyperparameters follow the HighwayEnv quickstart recipe:

| Parameter | Value |
| --- | --- |
| policy | `MlpPolicy`, `net_arch [256, 256]` |
| `learning_rate` | 5e-4 |
| `buffer_size` | 15000 |
| `learning_starts` | 200 |
| `batch_size` | 32 |
| `gamma` | 0.8 |
| `train_freq`, `gradient_steps` | 1, 1 |
| `target_update_interval` | 50 |
| `exploration_fraction` | 0.7 |
| `device` | `cpu` |

### Functions

- `train(timesteps, out, seed) -> Path`: builds the env and model, calls `model.learn`, saves to `out`, prints the elapsed minutes.
- `run_episode(model, seed) -> dict`: one greedy rollout (`predict(deterministic=True)`), returning `seed`, `return`, `crashed`, `mean_speed_mps` (from `info["speed"]`) and `steps`.
- `evaluate_checkpoint(path, seeds) -> dict`: loads the checkpoint on CPU and runs every seed; returns `model`, `episodes`, `mean_return`, `crash_rate`, `mean_speed_mps`, `mean_steps` and `per_episode`.
- `parse_seed_range(text) -> list[int]`: `"0-19"` or `"3,7,11"` or a mix. Also used by `backend/evaluate.py`.

### Flags and outputs

| Flag | Default | Meaning |
| --- | --- | --- |
| `--timesteps` | 20000 | Training steps |
| `--seed` | 0 | SB3 seed |
| `--out` | `models/dqn_highway_<N>k.zip` | Checkpoint path |
| `--eval-seeds` | `0-19` | Seeds for the post-training rollout |
| `--eval-only PATH` | none | Skip training, evaluate this checkpoint |
| `--promote` | off | Also copy the checkpoint to `models/dqn_highway.zip` |

`run_cli` trains unless `--eval-only`, evaluates, prints the summary without `per_episode`, writes `<checkpoint>.eval.json` next to the checkpoint, and copies to `DEFAULT_MODEL_PATH` when promoting. The `.eval.json` shape is in [Evaluation report](../contracts/eval-report.md).

```bash
uv run interlock train                                            # 20k steps
uv run interlock train --timesteps 100000 --promote               # the promoted run
uv run interlock train --eval-only models/dqn_highway_20k.zip     # score a checkpoint
```

The 100k run takes about 25 minutes on a laptop. Everything in `models/` except its README is gitignored, so each clone trains its own checkpoint or copies one in. The Docker build fails without `models/dqn_highway.zip` (see [Deployment internals](../deployment-internals.md)).

### Checkpoint selection

Greedy rollouts over seeds 0 to 19:

| Checkpoint | Crash rate | Mean speed | Mean steps of 60 | Mean return |
| --- | --- | --- | --- | --- |
| 20k | 0.85 | 27.3 m/s | 33.5 | 28.5 |
| 100k | 0.40 | 29.8 m/s | 52.0 | 50.7 |

The rule: keep the checkpoint with the lower crash rate while it still averages above 25 m/s, because a timid agent never breaks a rule and makes nothing to shield. The 100k checkpoint is faster and crashes less, so it is the promoted `models/dqn_highway.zip`.

## `backend/policy.py`

```python
@dataclass(frozen=True)
class RankedAction:
    name: str
    index: int
    q: float
    rank: int
```

`Policy` wraps a loaded `DQN`:

- `Policy.load(path=DEFAULT_MODEL_PATH)` calls `DQN.load(path, device="cpu")`.
- `q_values(obs) -> np.ndarray`: `model.policy.obs_to_tensor(obs)` then `model.q_net(obs_tensor)` under `torch.no_grad()`, squeezed to a float array in `ACTION_NAMES` order.
- `ranked_actions(obs) -> list[RankedAction]`: sorts indices by `(-q, index)` so ties keep action-index order, and assigns `rank` 0 to 4.

The shield needs the full ranking, not the argmax: when the top action is blocked, the next-best action is already in hand with no second forward pass. See [Shield algorithm](shield.md).

`tests/test_policy.py` uses an untrained `build_model(env, seed=0)` (arbitrary but deterministic Q-values) and checks that the ranking covers every action once in descending Q order, that `ranked_actions(obs)[0].index` equals `model.predict(obs, deterministic=True)` over several steps, and that Q-values are finite. One test loads the promoted checkpoint and skips when it is absent.

## `backend/paths.py`

Repo-relative paths shared by every module, so nothing hard-codes a working directory:

| Name | Value |
| --- | --- |
| `BACKEND_DIR` | `backend/` |
| `REPO_DIR` | repository root |
| `MODELS_DIR` | `models/` |
| `LOGS_DIR` | `backend/logs/` |
| `INTERNAL_DIR` | `internal/` |
| `DEFAULT_MODEL_PATH` | `models/dqn_highway.zip` |
| `ENV_FILE` | `backend/.env` |
