# Prompt Families

These are the default prompt families for OpenClaw long-form article illustration.

They are adapted for:

- Chinese long articles
- RunningHub image generation
- Feishu doc embedding
- 1-5 images max

Do not copy these mechanically.
Merge them with the concrete article angle and section purpose.

## 1. `cover-hero`

Use for:

- first-screen visual
- article cover
- opening mood

Best aspect ratio:

- `16:9`

Prompt skeleton:

```text
[主体场景]，作为公众号文章封面主视觉。
画面中心是 [核心对象/角色/系统]，正在体现 [文章主判断]。
整体风格 [风格词]，明亮，层次清晰，主体突出。
构图偏海报式，适合手机阅读首屏，留出适量留白。
强调 [关键词1]、[关键词2]、[关键词3]。
避免过暗、避免信息过满、避免廉价企业海报感。
```

## 2. `concept-illustration`

Use for:

- abstract idea made visible
- mid-article explanation
- one key concept per image

Best aspect ratio:

- `4:3`
- `3:4`

Prompt skeleton:

```text
围绕 [抽象概念] 的概念插图。
通过 [具体视觉隐喻] 表达 [概念含义]。
主体简洁，层级明确，读者一眼能看懂重点。
风格 [风格词]，画面干净，不要过度堆元素。
适合插在公众号正文中段，帮助解释概念。
```

## 3. `structure-infographic`

Use for:

- process
- comparison
- system relation
- framework explanation

Best aspect ratio:

- `16:9`
- `4:3`

Prompt skeleton:

```text
一张结构化信息图，用来说明 [流程/对比/框架]。
画面包含 [模块A]、[模块B]、[模块C] 的关系。
以 [颜色策略] 做分区，信息层级清楚，图形简洁。
整体风格 [风格词]，偏知识可视化而不是商业广告。
如果有文字，只保留极少量标签，不要大段排字。
```

## 4. `divider-scene`

Use for:

- section transition
- visual breathing room
- atmosphere shift

Best aspect ratio:

- `16:9`

Prompt skeleton:

```text
作为文章分节过渡图，围绕 [章节主题]。
画面更重氛围，不重信息密度。
构图舒展，元素较少，风格 [风格词]。
让读者读到这里时有一个视觉停顿。
```

## 5. `characterized-tech`

Use for:

- young tech/gamer article
- AI tools as角色化协作
- slightly anime/game energy

Best aspect ratio:

- `16:9`
- `4:3`

Prompt skeleton:

```text
年轻化科技插画，围绕 [技术主题]。
将 [系统/流程/工具] 表现成有协作感的角色化场景，但不过度卡通。
整体明亮、现代、带一点动漫或游戏 UI 气质。
强调 [动作]、[分工]、[信息流]，弱化廉价赛博朋克感。
```

## Banana-derived category hints

Useful categories adapted from the Nano Banana prompt collection:

- `Infographic / Edu Visual`
  - good for `structure-infographic`
- `Illustration`
  - good for `concept-illustration`
- `Anime / Manga`
  - good for `characterized-tech`
- `Sketch / Line Art`
  - good for minimal concept visuals
- `Poster / Flyer`
  - good for `cover-hero`
- `Product Marketing`
  - only use selectively for polished cover composition, not for over-commercial public-account visuals

