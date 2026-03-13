---
name: BLY-info-source-verifier
description: Use this skill whenever the info worker has candidate search results and must decide which sources are strong enough to support a real answer. Trigger for any web-search result review, official-vs-media judgment, noisy or ambiguous search hits, and especially when the next step could affect writer output. Prefer this skill before passing material to writer.
---

# BLY Info Source Verifier

This skill judges sources before they become evidence.

Use it after search and before summarization.

Its job is to stop weak search hits from becoming fake certainty.

## Core rule

Not every hit deserves to survive.

The verifier should reduce a pile of links into:

- trusted evidence
- supporting context
- weak or irrelevant noise

## Source tiers

Use these default tiers:

### Tier A: Official

Examples:

- official website
- official documentation
- official GitHub or GitLab
- official announcement page
- official social account

Use Tier A to define what something is.

### Tier B: Trusted media or technical publication

Examples:

- major international media
- well-known technical publications
- strong industry analysis sites

Use Tier B to add background, interpretation, or outside validation.

### Tier C: Community and secondary discussion

Examples:

- forum threads
- blog posts without clear provenance
- reposts
- newsletters citing others

Use Tier C only as supporting context or clue generation.

### Tier D: Weak or noisy source

Examples:

- SEO farms
- content mills
- vague aggregators
- pages that mention the phrase but do not answer the question

Do not use Tier D as evidence.

## Verification workflow

### Step 1: Judge relevance

For each candidate result, answer:

- does this page clearly concern the target topic
- does it answer the actual question
- is it about the same entity, not a name collision

If not, downgrade or discard it.

### Step 2: Judge authority

Then decide the tier:

- A official
- B trusted
- C secondary
- D weak

If uncertain between two tiers, choose the lower one.

### Step 3: Extract only grounded facts

From surviving sources, extract:

- entity definition
- concrete capabilities or claims
- release or date facts
- confirmed relationships

Do not extract speculative framing as fact.

### Step 4: Detect evidence weakness

Mark the result as weak if:

- no Tier A source exists
- only one weak Tier B/C source supports the claim
- multiple sources disagree about the basic identity of the topic
- the sources only discuss adjacent concepts

### Step 5: Decide answer readiness

Return one of:

- `ready_for_formal_answer`
- `ready_with_caution`
- `not_ready`

Use `not_ready` whenever the topic still cannot be defined clearly.

## Output format

Always return this structure:

```text
topic:

surviving_sources:
- title:
  domain:
  tier:
  why_it_survives:
  usable_facts:
    - ...

discarded_sources:
- title:
  domain:
  reason:

verified_facts:
- ...

open_questions:
- ...

answer_readiness:
- ready_for_formal_answer / ready_with_caution / not_ready

confidence:
- high / medium / low
```

## Red lines

Do not:

- keep a source only because it ranks high in search
- elevate community chatter above official facts
- pass weakly related pages downstream as evidence
- turn speculation into a clean definition

## Practical guidance

When the topic is a product, tool, model, API, or project, the lack of Tier A sources is a major warning sign.

When the topic is a breaking event, Tier B trusted media may be enough to continue cautiously if multiple independent sources agree.

## Templates and tests

Use [source-scorecard-template.md](templates/source-scorecard-template.md) for structured judging.

The evaluation prompts for this skill live in [evals.json](evals/evals.json).
