---
layout: post
title: "Four repos and a paper trail: structuring a research project"
date: 2026-09-23
description: "How I start a new research project: a one-page brief before any code, then the four-repo layout and the habits (decision records, experiment logs, hash-pinned evidence) that make six-month-old results explainable again."
tags:
  - research
  - reproducibility
  - workflow
  - computational-science
image: "/assets/images/posts/structuring-a-computational-research-project/bc3f1ba122.jpg"
---

![](/assets/images/posts/structuring-a-computational-research-project/bc3f1ba122.jpg)

Photo by [Nick Morrison](https://unsplash.com/@nickmorrison) on [Unsplash](https://unsplash.com)

Six months into a research project, someone asks a simple question: *which run produced the number in Figure 3?* If the honest answer involves scrolling a chat history, guessing which config file was live that week, or asking a collaborator to "check their laptop," the project has a structure problem, not a memory problem. This is the layout and the small set of habits I use to make sure that question always has a one-line answer.

None of this is exotic. It borrows more from software engineering (version control, checksums, changelogs) than from anything specific to research. The point isn't process for its own sake; it's that six months is longer than anyone's working memory, and a paper claim that can't be traced back to an exact run isn't a claim, it's a recollection.

### Start with the brief, not the repo

The habit that matters most comes before any of the ones below, and before the project exists at all: a new idea gets a one-page brief before it gets a workspace. Not a summary written afterward for people who didn't read the full proposal. It is the *first* document, written specifically so a collaborator can say "go" or "here's what's missing" in the time it takes to read one page, before either of you has invested in scaffolding or a ten-page write-up that might not survive the first question.

The layout is the same every time: the question at the top, stated fairly enough that either a positive or a negative result would be a real outcome; a short list of what's actually needed *from the reader specifically*; then a staged plan where each stage states three things: the question it settles, what it hands the next stage, and the condition under which it would end the project outright. A section spelling out what's deliberately **not** being done heads off half the follow-up questions before they're asked. No dates, no calendar. Stages are ordered by dependency, and scheduling is a separate conversation once people agree on the sequence. It ends with a short numbered list of exactly what's blocking, so the first reply can be "here's #1" instead of a paragraph of caveats.

Visually it's plain: a one-color masthead, a callout box for the summary, and one card per stage, built with a small reusable LaTeX template so the formatting decision only gets made once. A colour-blind-safe palette and a status badge (go / stop / blocking) do the work that would otherwise take a paragraph of hedging. A stage that's a clear stop condition is more useful in red than in a sentence starting with "note that."

![Wireframe of a one-page action brief: a masthead, a TL;DR and input box, four stage cards with go, stop, and blocking status, and a numbered ask list](/assets/images/posts/structuring-a-computational-research-project/brief-mockup.svg)

*Shape of the one-pager, not real content (by author).*

The same format works the other way round too, once a project already has a full proposal: distill it into a one-pager for the people who were never going to read the whole thing. But starting with the brief, before the long document, before the workspace, is the version that saves the most time. It's the cheapest place to find out an idea needs rethinking.

Only once the brief has a "go" does the rest of this apply.

### One workspace, four repos, four jobs

A project lives across four repos, each with one job and a boundary that doesn't get crossed:

```
workspace/
  AGENTS.md            ← entry point: what's where, house rules
  project-code/         ← implementation (public, runnable, git)
  project-paper/        ← manuscript, figures, tables (git)
  project-research/     ← private notebook: plans, logs, decisions (git)
  project-artifacts/    ← large run outputs (outside git)
```

![Workspace flow: the one-page brief feeds project-research, which promotes stable code, large outputs, and polished text into project-code, project-artifacts, and project-paper](/assets/images/posts/structuring-a-computational-research-project/workspace-layout.svg)

*Workspace flow (by author). Edit `workspace-layout.mmd` in the same folder and run `make diagram-research-project-structure` to regenerate the SVG.*

**Code** stays runnable and public from day one. No half-finished analysis branches leak into it. **Paper** only receives material once it's polished enough to be reviewer-facing; a rough figure doesn't belong there just because it's convenient. **Research** is the messy private notebook: the place for a plan that might be wrong, a critique of your own prior-art search, a decision you reversed a week later. **Artifacts** holds anything too large or too binary for git (checkpoints, raw logs, full result sets), referenced by path and hash and never committed.

The boundary that matters most: nothing gets promoted to `paper` or `code` until it's stable, and nothing large ever goes into git. Both rules exist because the opposite failure mode (a `git log` full of half-baked WIP, or a repo too large to clone) is what makes people stop trusting the history.

### Every artifact gets a hash

A results directory gets overwritten by the next run constantly. That's normal and fine, right up until someone needs the *previous* run's numbers for a rebuttal. So before anything gets overwritten, it gets archived, named with a timestamp, and hashed:

```bash
TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
ARCHIVE="experiment_slug_${TIMESTAMP}.tar.gz"

tar -czf "artifacts/${ARCHIVE}" results/ configs/run_config.json scripts/run.py
shasum -a 256 "artifacts/${ARCHIVE}" | tee "artifacts/${ARCHIVE}.sha256"
```

The rule is one archive per run, never overwritten, checksum stored next to it. It costs nothing at run time and turns "I think that's the same run" into a `shasum -c` that either passes or doesn't.

### One file per decision, including the obvious ones

Every non-trivial choice (a baseline, a hyperparameter, a metric definition) gets a short dated file:

```markdown
# Decision: <title>
Date: YYYY-MM-DD · Status: accepted

## Context
What forced this decision?

## Decision
One clear sentence.

## Rationale
Why this, not the alternative: trade-offs considered.

## Consequences
- Positive: what this enables
- Negative: what this rules out
- Follow-up: what has to happen because of it
```

The habit that actually pays off is writing these even for choices that feel obvious at the time. Obvious-now is not obvious-in-six-months, and a reviewer will ask exactly the question you didn't think needed answering. One decision per file, and the rejected alternative always gets a sentence. A decision record that only shows what was chosen, with nothing about what wasn't, doesn't tell you anything a comment in the code couldn't.

### Every number in the paper traces back to a hash

Two more templates close the loop. An **experiment log** is one file per run, written *before* the run with the question it's meant to answer, then filled in after with the exact command, the commit SHA, and the resulting artifact hash. An **evidence table** is one row per paper-facing claim, pinning it to the specific archive and checksum that backs it:

```markdown
| Role                    | Path                          | SHA256   | Pinned    |
|-------------------------|--------------------------------|----------|-----------|
| Final benchmark archive | `artifacts/final_20260912.tar.gz` | `a1b2c3…` | ✓ 2026-09-12 |
```

A short script re-hashes every pinned archive against this table and fails loudly on a mismatch. Running it before a submission answers, mechanically, whether every number in the manuscript still points at the file that produced it, instead of trusting that it does.

### What this buys you

None of these habits are free. A decision record takes five extra minutes over just making the call, and an evidence table takes discipline to keep current. What they buy back is larger: a project that outlives your own memory of it, and, further back, one that never got scaffolded in the first place if the one-page version couldn't get a "go." Six months in, "which run produced Figure 3" is a `grep` through `artifacts_index.md`, not an archaeology project. A reviewer's "why this baseline and not that one" has a file with a date on it. And the collaborator who only has two minutes gets a page that tells them exactly what you need, instead of a folder they'd have to spelunk through to figure it out themselves.

I packaged all of this (the brief, the workspace layout, the experiment log, the decision record, the artifact-archive checklist) as installable [Claude Code](https://claude.com/claude-code) skills, in the order a new project actually uses them: [github.com/jkrajniak/research-skills](https://github.com/jkrajniak/research-skills). `/plugin install research-skills` gets you the same habits without retyping any of the above.
