---
name: BLY-writer-illustration-planner
description: Use this skill whenever a long article needs 1-5 supporting images, cover art, or inline illustrations planned before calling RunningHub. Trigger for requests mentioning 配图、封面图、插图、长图文、图文版公众号, or whenever a writer draft already contains image placeholders and needs concrete prompts and placement guidance.
---

# BLY Writer Illustration Planner

This skill plans article visuals.

It does not replace `runninghub-image`.

Its job is to decide:

- how many images are worth generating
- where they should appear
- what each image should depict
- what prompt should be sent to RunningHub

Use [references/prompt-families.md](references/prompt-families.md) for reusable prompt families.
Use [references/style-router.md](references/style-router.md) for style and role selection.

## Core principle

Images should help the article, not decorate it blindly.

If the article is already clear without many visuals, use fewer images.

Default useful range:

- `1-3` images for most articles
- up to `5` only when the article clearly has multiple scene changes or concept blocks

Do not follow a "more is always better" rule.
For this production setup, fewer but better images is the default.

## Planning workflow

### Step 1: Read the article structure

Identify:

- opening scene
- key concept sections
- emotionally strongest paragraph
- places where visual contrast helps

### Step 2: Choose image roles

Common roles:

- cover / first-screen visual
- concept illustration
- section-divider visual
- closing mood image
- infographic / structural visual

Do not assign every paragraph a separate image.

Prefer role selection inspired by the article-illustrator method:

- `cover`
  - opening mood, first-screen pull, core stance
- `concept`
  - abstract idea made visible
- `structure`
  - process, comparison, framework, system relation
- `divider`
  - visual breathing room between major sections

For most公众号长文, choose from:

- 1 image: `cover`
- 2 images: `cover + concept`
- 3 images: `cover + concept + structure`
- 4-5 images only when the article truly has multiple heavy sections

### Step 3: Bind to markers

Match each planned image to a marker:

- `{{IMAGE_1}}`
- `{{IMAGE_2}}`
- `{{IMAGE_3}}`
- `{{IMAGE_4}}`
- `{{IMAGE_5}}`

Only output markers that are actually needed.

## Prompt style

Prompts for RunningHub should be:

- concrete
- visual
- style-aware
- consistent with the article tone

Prefer describing:

- scene
- subject
- lighting
- composition
- mood
- visual style
- camera or framing cue when useful
- what should stay simple

Build prompts by combining:

1. a `role family` from [references/prompt-families.md](references/prompt-families.md)
2. a `style profile` from [references/style-router.md](references/style-router.md)
3. the article's concrete concept

The final prompt should feel like a real image brief, not a pile of tags.

Avoid vague prompts like `科技感海报`.

## Output format

Return a JSON array or object with entries like:

```json
[
  {
    "slot": 1,
    "marker": "{{IMAGE_1}}",
    "purpose": "opening cover",
    "visual_family": "cover-hero",
    "style_profile": "bright-tech-youth",
    "placement_hint": "after the opening section",
    "caption": "封面图：AI 工作流像一支协同出击的小队",
    "prompt": "明亮的未来科技插画，数个年轻化AI角色在指挥台协作...",
    "aspect_ratio": "16:9"
  }
]
```

## Visual direction for this project

Default direction:

- bright modern tech
- youthful but not childish
- a little anime/game energy when suitable
- avoid dark corporate sci-fi by default

Default families for this project:

- `cover-hero`
- `concept-illustration`
- `structure-infographic`

Default styles for this project:

- `bright-tech-youth`
- `clean-line-notion`
- `light-anime-tech`

Only switch to darker or heavier aesthetics when the article itself is serious, controversial, or intentionally cinematic.

## Practical adaptation from external references

This skill may borrow methodology from:

- `baoyu-article-illustrator`
  - role planning
  - style routing
  - position-aware image planning
- Nano Banana prompt libraries
  - prompt category vocabulary
  - use-case grouping
  - visual pattern inspiration

But keep the final output aligned to this stack:

- Chinese public-account article
- RunningHub execution
- Feishu doc delivery
- 1-5 image production budget
- young tech/gamer voice

## Pairing

This skill is usually followed by:

- `runninghub-image` for execution
- `feishu-cloud-doc` after image URLs are inserted into the article
