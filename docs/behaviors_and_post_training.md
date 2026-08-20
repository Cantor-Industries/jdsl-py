# Behaviors and post-training

> A design note, not a shipped feature. It argues that a jdsl tree is useful in
> two places, not one: at **inference time** as a controller, and at **train
> time** as a source of supervision — and that the same tree serves both.

## The question

Gemma-4 E2B scores ~24% on τ-bench retail. The mission we keep circling is:
*jdsl should make a small model do better on tasks like this.* So far we have
only used one lever — **structure the inference**: put the policy in guards the
model can't step around, hand it the right tools at the right time, remember its
failed calls. That is real, and it is free (no weights change). But it has a
ceiling, and the interesting question is whether the *same* tree can also drive
the other lever — **change the weights** — and whether that is a coherent thing
to build.

The short answer: yes, and it is the natural next axis of the project. But only
if we are honest about which of the model's problems structure can fix and which
ones only weights can.

## Two levers, one wall between them

There are exactly two ways to get better behavior out of a fixed architecture:

| Lever | What it buys | What it cannot buy |
| ---- | ---- | ---- |
| **Structure** (inference-time) | Reliability, format-adherence, policy compliance, "never write before confirm" | New capability the base weights don't have |
| **Weights** (post-training) | Native competence at a skill — the model just *does* it | A *guarantee* — weights encode a tendency, never an invariant |

The wall between them is the **capability floor**, and we have already hit it
concretely. On task 0, the 2B model dropped the `#` from `#W2378156` and called
`get_order_details` with `W2378156`. No prompt, no guard, no tool schema fixes
that — the model genuinely cannot reliably preserve that token. Structure routed
it to the right tool at the right moment; it still fed the tool a wrong argument.
**That is a weights problem wearing a structure problem's clothes.** Structure
got us to the floor fast and cleanly — which is exactly why it is a good
instrument for *finding* the floor. Everything below the floor is post-training's
job.

So the goal "jdsl improves small-model scores" makes sense, but it splits in two:
push the floor down with better structure (what we have), and lift the model up
to the floor with post-training (what this note is about).

## The idea that makes post-training a jdsl feature

Here is the load-bearing observation. A jdsl tree does not just run a task — it
**decomposes** it into typed, individually-checkable sub-decisions:

```
auth gate            → a lookup happened and returned a user id   (checkable)
intent classifier    → predict("transcript -> intent")            (a label)
confirmation gate     → deterministic read of the transcript       (already correct, no model)
per-intent action    → react("transcript -> reply", tools=…)      (a trajectory, gradeable by env)
```

Each leaf is a **narrow supervised signal**. That changes what "collect training
data for this agent" means. You are not distilling one opaque end-to-end policy;
you are distilling a handful of small skills, each of which you can collect data
for, **verify in isolation**, and recompose. The tree is a *curriculum*, and its
topology is a *labeling function*.

This is the whole thesis of the note: **a behavior tree is a specification that
can drive both inference and supervision.** The control flow you wrote to
constrain the model at run time is also the schema that tells you what data to
collect and how to grade it.

Three consequences fall out of that, in increasing order of ambition.

### 1. Reward-filtered trajectory distillation (near-term, precedented)

Run the tree on a *strong* model over the τ-bench **train** split. τ-bench grades
by final DB state, so every episode comes with a free 0/1 label. Keep only the
reward-1 rollouts; each is a gold trajectory — the exact tool calls and replies
that solved the task. SFT the small model on those.

This is [rejection-sampling fine-tuning / STaR] in all but name, and it works
because the verifier is real (env state, not a judge model). What jdsl adds is
that the tree already produced *clean, policy-compliant* trajectories to learn
from: the strong model never wrote before confirming, because the tree wouldn't
let it, so the small model learns a policy-correct habit rather than the strong
model's occasional shortcut.

### 2. Per-leaf distillation and compilation (medium-term)

Because the tree factorizes the task, you can train each leaf separately instead
of end-to-end:

- The **intent classifier** (`transcript -> intent`) is a tiny text-classification
  dataset. Collect it once, grade it directly (no rollout needed), distil a 2B
  model to near-100% on it. It never needs the whole episode.
- The **confirmation gate** needs *no* model at all — it is already a deterministic
  string check. That is a skill you get for free and never pay to train.
- The **react leaves** are tool-calling trajectories, gradeable by the env.

This is the same move DSPy makes when it *compiles* a program against a trainset
(`BootstrapFewShot` optimizes demos per module; `BootstrapFinetune` distils a
module into weights). jdsl trees are a superset of a DSPy pipeline — they add
control flow and state — so "compile the tree" means: fix the topology, optimize
each leaf's demos/instructions against the trainset with the env reward as the
metric, and optionally fine-tune each leaf into its own small adapter. Failures
localize to a leaf, so you always know *which* skill to collect more data for.

### 3. Compiling behaviors *from* datasets (speculative)

The inverse of everything above: given a dataset of trajectories, *induce* the
tree — learn not just the leaf prompts but the topology (which checks, which
gates, which routing). This is program induction over the tree DSL. It is the
research end of the spectrum and we should treat it as such; the honest near-term
version is "human authors the topology, the dataset optimizes the leaves,"
because the topology is where the *guarantees* live and we do not want those
learned probabilistically (see below).

## The real design principle: what stays structure, what becomes weights

Post-training does not *replace* the tree. It changes the **division of labor**
inside it. The question for every behavior is: do I want this **guaranteed** or
merely **likely**?

| Behavior | Keep as… | Why |
| ---- | ---- | ---- |
| auth-before-any-action | **structure** (guard) | a safety invariant; must hold 100% of the time, even for a perfectly tuned model |
| confirm-before-write | **structure** (guard) | same — a probabilistic "usually confirms" is a liability, not a feature |
| recognizing intent | **weights** | a competence; distil it so the small model just knows it |
| formatting `#W2378156` correctly | **weights** | pure capability; the floor we actually hit |
| phrasing the reply | **weights** | fluency, no guarantee needed |

Structure encodes the invariants you need **guaranteed**; weights encode the
competence you want **cheap and native**. As the small model gets better at the
"weights" rows, you can *dissolve* the soft scaffolding that was propping it up —
the coaching instructions, the failed-call reminders — because it has internalized
them. But you keep the load-bearing guards forever, no matter how good the model
gets, because their whole value is that they are not probabilistic. This is
**progressive scaffold removal**: the tree starts as a full exoskeleton for a
weak model and ends as a thin frame of hard guarantees around a competent one.

## So: is the goal plausible?

| Claim | Verdict |
| ---- | ---- |
| A jdsl tree can lift a small model's score on tasks like τ-bench | **Plausible and precedented** — via reward-filtered trajectory distillation from a strong model + tree |
| The tree makes that distillation more sample-efficient and verifiable | **Plausible** — it factorizes the task into per-leaf, independently-gradeable skills |
| Behaviors can be "as concrete as fine-tuning" | **Half true** — the tree *generates and grades* the fine-tuning data; it does not itself substitute for weights past the capability floor |
| We can compile behaviors from datasets | **True for leaves, research for topology** — DSPy-style leaf optimization is near-term; inducing the tree structure is not |

The mission is coherent, and it has a clean shape: **structure finds and enforces
the floor; post-training, driven by the same structure, lifts the model to it.**
The tree is the artifact that ties the two together — a controller at inference,
a curriculum at train time.

## The smallest experiment that would test this

We already have the machine to try step 1 end-to-end, because the τ-bench adapter
runs the tree and returns the env reward:

1. Run `--arm tree` on the retail **train** tasks with the strongest model we can
   reach (even a hosted one, once), logging every `Session` transcript + tool
   trace + final reward.
2. Keep the reward-1 episodes; render each into SFT examples (system, messages,
   tool calls) — one per react-leaf turn.
3. LoRA-tune Gemma-4 E2B on them.
4. Re-run `--arm tree` with the tuned model and compare pass^k to the 24% baseline.

If the tuned small model closes even part of the gap on the *train distribution*,
the core claim holds and the per-leaf refinements (step 2) are worth building.
And the first thing to watch is whether it learns to keep the `#` — that single
token is the cleanest yes/no on whether distillation crossed the floor structure
could not.
