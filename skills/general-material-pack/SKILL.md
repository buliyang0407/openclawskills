---
name: general-material-pack
description: Use this skill whenever the writer should quickly turn a topic into a concise, practical material pack and a directly usable short article. This is the default skill for requests like “写一篇功能介绍”, “整理一份素材”, “做一个简洁介绍”, “写个 1000 字内的说明”, or “先帮我把这个主题讲明白”. Prefer this skill for short explanatory articles, product/function introductions, work-summary style drafts, and practical briefing content.
---

# General Material Pack

Use this skill when the user wants something clear, usable, and not too long.

This skill is intentionally practical:

- assemble the topic fast
- identify the few facts that matter
- give a clean structure
- produce a short article the user can send, edit, or continue expanding

## Default promise

Unless the user says otherwise, output a Chinese article of about `600-1000` Chinese characters.

If the topic is especially small, it is fine to be shorter.
If the topic is more complex, stay under `1000` Chinese characters unless the user explicitly asks for more.

## When to use it

Use this skill whenever the user asks for:

- a concise introduction
- a function overview
- a short article
- a practical explainer
- a first draft about a topic
- a material pack that can immediately become an article

Typical examples:

- “写一篇关于 Codex 的功能介绍”
- “帮我整理这个主题，写成一篇短文”
- “给我一个简洁直接的介绍稿”
- “做一份通用素材包”
- “先写一版 1000 字以内的说明”

## Core workflow

### Step 1: Decide the article frame

First determine:

- topic
- target reader
- purpose
- desired tone

If the user did not specify these, use the following defaults:

- target reader: 普通中文互联网读者 / 非专业但愿意了解的人
- purpose: 让人快速看懂是什么、有什么用、为什么值得关注
- tone: 简洁、直接、像人写的

### Step 2: Build a compact material pack

Before drafting, organize the topic into four blocks:

1. `主题定位`
2. `核心功能 / 核心事实`
3. `实际价值`
4. `适用场景 / 使用建议`

Do not dump every fact you know. Keep only the facts that help the article become clearer.

### Step 3: Write the article

Default article structure:

1. opening定位
2. what it is
3. what it can do
4. why it matters
5. practical closing / suggestion

The article should feel like:

- one clear thought
- three to five useful points
- a natural ending

## Output modes

### Default mode

If the user just says “写一篇”, output:

```text
标题：

正文：
```

Only include the article itself unless the user asks to see the material pack.

### Material-pack mode

If the user explicitly says “整理素材”, “做素材包”, or wants the intermediate structure, output:

```text
主题定位：

核心要点：
1. ...
2. ...
3. ...

建议结构：
1. ...
2. ...
3. ...

参考成稿：
...
```

### Hybrid mode

If the user wants both clarity and direct usability, output:

```text
标题：

一句话定位：

核心要点：
- ...
- ...
- ...

正文：
...
```

## Writing rules

- Prefer short, clean paragraphs.
- Avoid fake grand claims.
- Avoid excessive jargon.
- Avoid bullet-heavy final articles unless the user explicitly wants list format.
- Keep the rhythm natural and readable.
- Do not sound like generic AI marketing copy.
- Prefer concrete verbs over empty adjectives.

## Source use

When knowledge-layer material is already provided, use it first.

When fresh outside information is clearly needed, use info-layer supplements if available.

If no extra material is provided and the request is a common explanatory article, it is acceptable to draft from the writer's current knowledge, but do not pretend you verified fresh facts.

## What good output looks like

For a request like “写一篇关于 Codex 的功能介绍”, the result should:

- explain what Codex is
- mention its key capabilities
- explain why it is useful
- feel readable in one sitting
- stay around 1000 Chinese characters or less

## Failure handling

If the topic is too vague, do not ask a long list of questions.

Make one practical assumption and keep going.

If the topic truly cannot be explained without key missing context, ask for only the single most important missing detail.

## Writer pairing

This skill pairs well with:

- `voice-editor` when the draft should sound more like the user's own voice
- `feishu-cloud-doc` when the result should land in Feishu Docs
- `runninghub-image` when the article also needs a cover or supporting visual
