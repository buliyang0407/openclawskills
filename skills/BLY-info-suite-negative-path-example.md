# BLY Info Suite Negative-Path Example

This example simulates the exact kind of failure we want to prevent:

- the topic is ambiguous
- no official source is found
- weak search hits exist
- writer must not receive a "go ahead and write a formal intro" signal

## Step 1: search planner output

Prompt:

`帮我搜一下 nano banana 是什么，后面要写介绍稿。`

Expected planner-style output:

```text
topic: nano banana
lookup_type: ambiguous_unknown
goal: determine whether nano banana is a real product, project, model, or named concept with enough public evidence for a short introduction

query_lanes:
- official:
  - nano banana official
  - "nano banana" official site
  - "nano banana" official docs
- definition:
  - "nano banana" what is
  - "nano banana" product
  - "nano banana" tool
- release_or_news:
  - "nano banana" release
  - "nano banana" announcement
- docs_or_repo:
  - "nano banana" github
  - site:github.com "nano banana"
- trusted_media:
  - "nano banana" tech news
  - "nano banana" ai tool
- disambiguation:
  - "nano banana" hardware
  - "nano banana" software
  - "nano banana" AI

source_priority:
- official
- trusted_media
- community

stop_conditions:
- no official or clearly authoritative source found
- results remain ambiguous after disambiguation search
- no page clearly answers what nano banana is
```

## Step 2: source verifier output

Input assumption:

- no official site found
- one generic AI page that only mentions the phrase
- one broad media page about AI trends
- one weak aggregator page

Expected verifier-style output:

```text
topic: nano banana

surviving_sources:
- title: Generic AI trend page
  domain: example-tech-media.com
  tier: C
  why_it_survives: mentions the phrase but does not define the entity
  usable_facts:
    - only proves the phrase appears in discussion

discarded_sources:
- title: Broad AI landing page
  domain: example-news.com
  reason: about adjacent AI topics, not nano banana itself
- title: Aggregator repost
  domain: example-aggregator.com
  reason: unclear provenance and no direct factual definition

verified_facts:
- no official source was found
- the topic cannot yet be defined clearly from surviving sources

open_questions:
- what entity nano banana refers to
- whether it is a real product, a nickname, or a stray phrase

answer_readiness:
- not_ready

confidence:
- low
```

## Step 3: evidence pack output

Expected final handoff:

```text
topic: nano banana
retrieval_goal: determine whether a formal introduction article can be grounded in public web evidence

source_summary:
- official_hits: 0
- trusted_hits: 0
- supporting_hits: 1

grounded_facts:
- no official source found
- no trusted media source clearly defines the topic
- surviving evidence is too weak to identify the entity

usable_sources:
- source: generic phrase mention
  tier: C
  value: weak clue only, not suitable for formal definition

open_questions:
- what nano banana actually is
- whether there is a primary official source

risk_notes:
- high hallucination risk if writer is asked to produce a formal introduction
- current search evidence does not support clean definition or capability claims

handoff_decision:
- formal_writing_not_recommended

confidence:
- low
```

## Why this example matters

If the suite behaves like this, the chain stops in the right place:

- search planner widens the search instead of staying shallow
- source verifier rejects noisy hits
- evidence pack explicitly blocks formal writing

That is the intended fix for the earlier Nano Banana failure mode.
