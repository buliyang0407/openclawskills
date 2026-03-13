# BLY Info Skills Self-Test Notes

This suite is meant to protect the `info` worker from weak search behavior.

## Qualitative acceptance targets

### Scenario A: ambiguous new topic

Prompt:

`帮我搜一下 nano banana 是什么，后面我要写介绍稿。`

Expected behavior:

- planner treats the topic as ambiguous
- verifier refuses weak, off-topic, or speculative pages
- evidence pack returns `formal_writing_not_recommended`

### Scenario B: known product/tool

Prompt:

`查一下 OpenAI Codex 现在能做什么，后面我要写一篇 1000 字介绍。`

Expected behavior:

- planner prioritizes official docs / releases / repo lanes
- verifier keeps official sources as Tier A
- evidence pack returns `formal_writing_ok` or `formal_writing_with_caution`

### Scenario C: date-sensitive event

Prompt:

`看看最近特朗普和伊朗有什么新动态。`

Expected behavior:

- planner builds latest / statement / timeline lanes
- executor prefers stronger web_search discovery before fallback routes
- verifier requires multiple trusted sources
- news verifier checks publish date vs event date
- evidence pack preserves open questions and risk notes

## Mechanical checks

Run:

```powershell
python D:\clawlearn\openclawskills_repo\skills\BLY-info-suite-selftest.py
```

Pass conditions:

- every skill has matching frontmatter
- every skill has a template
- every skill ships with at least three eval prompts
- every skill contains a workflow or output section
