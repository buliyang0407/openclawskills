# Style Router

This file helps map article tone to a small, stable style set.

Do not expose style selection as a huge open-ended choice unless the user explicitly asks.
Pick the closest default and keep going.

## Default style profiles

### 1. `bright-tech-youth`

Use for:

- AI tools
- workflow articles
- efficiency / product commentary
- your current default voice

Visual traits:

- bright background or clear midtone background
- cool blue / cyan / white base
- modern interface-like composition
- energetic but not noisy

Avoid:

- dark cyberpunk overload
- enterprise stock-photo feel

### 2. `clean-line-notion`

Use for:

- concept explanations
- lightweight knowledge visuals
- simple process diagrams

Visual traits:

- line art or light geometric illustration
- lots of whitespace
- restrained palette
- easy to embed in正文

Avoid:

- photorealistic clutter
- too many decorative elements

### 3. `light-anime-tech`

Use for:

- young, playful, tech/gamer tone
- AI roleplay metaphors
- scenes with teamwork or personified systems

Visual traits:

- mild anime influence
- bright and youthful
- soft character emphasis
- modern digital mood

Avoid:

- childish mascot overload
- heavy fan-art imitation

### 4. `calm-structure`

Use for:

- comparison charts
- frameworks
- serious explanation sections

Visual traits:

- controlled composition
- modular layout
- low-noise background
- clearer visual hierarchy than emotional expression

Avoid:

- cinematic drama
- excessive glow effects

## Style selection rules

If the article is mainly:

- tool/product/AI commentary -> `bright-tech-youth`
- concept explanation -> `clean-line-notion`
- young/gamer/anime-inflected personal post -> `light-anime-tech`
- process/comparison/framework -> `calm-structure`

If two styles both fit:

- use the more readable one for inline images
- use the more expressive one only for the cover

## Role x style recommendations

- `cover-hero`
  - prefer `bright-tech-youth` or `light-anime-tech`
- `concept-illustration`
  - prefer `clean-line-notion` or `light-anime-tech`
- `structure-infographic`
  - prefer `calm-structure` or `clean-line-notion`
- `divider-scene`
  - prefer the same family as the cover, but simpler

## Borrowed method notes

Inspired by the role-first planning in `baoyu-article-illustrator`:

- decide image role first
- choose style second
- write prompt third

This order prevents pretty-but-useless images.
