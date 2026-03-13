---
name: BLY-info-evidence-pack
description: Use this skill whenever the info worker must hand clean, structured evidence to main or writer after search and source verification. Trigger for any request that needs a reliable summary, evidence handoff, grounded fact list, confidence label, or a clear "not enough evidence" result. This skill is the default final packaging step for open-web retrieval.
---

# BLY Info Evidence Pack

This skill turns verified search work into a compact evidence handoff.

Use it after:

- a search plan exists
- search has been executed
- candidate results have been verified

Its job is to make downstream writing safer and simpler.

## Core rule

Info should hand over evidence, not vibes.

The pack must tell the next worker:

- what was searched
- what survived
- what is actually confirmed
- what is still missing
- whether formal writing is safe

## When to use it

Use this skill whenever info is about to report back to:

- `main`
- `writer`
- a future review worker

Especially use it when:

- the topic is new or ambiguous
- the results are mixed-quality
- writer may otherwise over-assume

## Evidence-pack workflow

### Step 1: State the task

Capture:

- topic
- retrieval goal
- search posture such as product intro, current event, technical background, or reputation scan

### Step 2: Summarize what was actually found

Count, do not imply:

- official hits
- trusted-media hits
- supporting hits

If counts are weak, say so plainly.

### Step 3: List grounded facts only

Create a short list of facts that survive source verification.

Good facts:

- clear entity definition
- confirmed capability
- dated release statement
- confirmed relationship between entities

Bad facts:

- broad assumptions
- "probably means"
- category guesses

### Step 4: Preserve uncertainty

Always include:

- open questions
- weak points
- missing links

This prevents the writer from treating gaps as certainty.

### Step 5: Make the handoff decision

Return one of these conclusions:

- `formal_writing_ok`
- `formal_writing_with_caution`
- `formal_writing_not_recommended`

Use the third option whenever the topic still lacks a clear definition or strong evidence base.

## Output format

Always use this structure:

```text
topic:
retrieval_goal:

source_summary:
- official_hits:
- trusted_hits:
- supporting_hits:

grounded_facts:
- ...

usable_sources:
- source:
  tier:
  value:

open_questions:
- ...

risk_notes:
- ...

handoff_decision:
- formal_writing_ok / formal_writing_with_caution / formal_writing_not_recommended

confidence:
- high / medium / low
```

## Default phrasing discipline

Prefer plain, compact language.

Say:

- "No official source found"
- "Only one trusted source found"
- "The topic remains ambiguous"

Do not say:

- "It may be several kinds of product"
- "Probably refers to"
- "Likely means" unless clearly marked as a hypothesis

## Writer protection

If the handoff decision is `formal_writing_not_recommended`, state it clearly.

Do not soften it into a vaguely positive summary.

The goal is not to be agreeable. The goal is to keep downstream writing grounded.

## Templates and tests

Use [evidence-pack-template.md](templates/evidence-pack-template.md) when building the final handoff.

The evaluation prompts for this skill live in [evals.json](evals/evals.json).
