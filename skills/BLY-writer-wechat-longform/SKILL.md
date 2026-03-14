---
name: BLY-writer-wechat-longform
description: Use this skill whenever the writer should produce a real WeChat/public-account long article instead of a short intro. Trigger for requests like 写公众号、写长文、写长图文、写推文、做深度稿、做专题文章、带配图的文章、出可发云文档版本. It should generate a structured long-form article package for downstream image insertion and Feishu doc delivery.
---

# BLY Writer WeChat Longform

This skill is for full-length public-account articles.

It does not do search by itself.
It assumes `main` has already arranged:

- realtime info when needed
- knowledge supplements when available

Its job is to turn those materials into a publishable long-form article package.

## Default promise

Unless the user clearly wants another length, output a Chinese article of about `1800-3000` Chinese characters.

It should feel like:

- one complete post
- readable on phone
- suitable for Feishu doc delivery
- easy to continue editing

## Use this skill for

- public-account articles
- long explainers
- opinionated AI/tool posts
- mixed "search + write" article requests
- long drafts that also need image slots

Do not use this as the default for short intros or 600-1000字 briefers. Those should still prefer `general-material-pack`.

## Core workflow

### Step 1: Lock the article angle

First settle these silently from the request and materials:

- target reader
- main judgment
- article promise
- whether this is explanation / commentary / recommendation / comparison

The article must have one central viewpoint. Do not dump raw notes.

### Step 2: Build the outline

Prefer a compact structure like:

1. opening hook
2. problem or context
3. core analysis
4. practical judgment
5. closing takeaway

If the topic is more analytical, use 3-5 section headings.

## Step 3: Reserve image slots

When the downstream workflow will generate images, place explicit markers in the markdown:

- `{{IMAGE_1}}`
- `{{IMAGE_2}}`
- `{{IMAGE_3}}`
- `{{IMAGE_4}}`
- `{{IMAGE_5}}`

Only place as many markers as the article naturally needs.

Good positions:

- after the opening hook
- before a major section switch
- where a concept benefits from visual aid

Do not stack all image markers together.

## Step 4: Write for phone reading

Prefer:

- short paragraphs
- clean headings
- smooth transitions
- strong first screen

Avoid:

- giant walls of text
- over-citation in the prose
- dry report formatting

## Source discipline

When materials include realtime search results:

- treat them as the primary factual layer by default
- use knowledge material for history, previous records, and continuity

Only switch to knowledge-only writing when the user explicitly said so.

Do not present unverified fresh facts as settled truth.

## Output format

Return one strict JSON object when the caller asks for structured output.

Recommended schema:

```json
{
  "title_options": ["...", "...", "..."],
  "chosen_title": "...",
  "summary": "...",
  "markdown_article": "...",
  "cover_prompt": "...",
  "image_slots": [
    {
      "slot": 1,
      "marker": "{{IMAGE_1}}",
      "purpose": "opening cover",
      "caption": "...",
      "prompt": "...",
      "aspect_ratio": "16:9"
    }
  ]
}
```

If the caller does not require JSON, still think in this structure internally.

## Title style

Prefer 3-5 titles with slightly different angles:

- direct judgment
- problem-driven
- contrast / anti-common-sense

Do not make them cheap clickbait.

## Pairing

This skill pairs naturally with:

- `BLY-writer-style-young-tech`
- `BLY-writer-illustration-planner`
- `feishu-cloud-doc`

