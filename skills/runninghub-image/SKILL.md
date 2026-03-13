---
name: runninghub-image
description: Use this skill whenever the user wants the writer to generate an image, cover, illustration, poster visual, concept art, or article配图 through RunningHub. This skill is especially relevant for Chinese content workflows where the writer should turn a text idea into a real hosted image URL instead of only describing the image.
---

# RunningHub Image

Use this skill when the task is to actually generate an image, not merely to suggest a prompt.

## What this skill does

- Turns a text prompt into a RunningHub image task
- Polls RunningHub until the task finishes
- Returns a stable result payload with the hosted image URL
- Supports article cover images, inline illustrations, poster concepts, and social visuals

## When to use it

Use this skill whenever the user asks for:

- 生图
- 配图
- 封面图
- 插画
- 海报视觉
- 根据文章内容画一张图
- 给这篇材料做个封面

If the user only wants help refining a prompt, you may still use this skill to structure the prompt, but do not claim the image was generated unless the script succeeded.

## Workflow

1. Confirm the intended image goal in one sentence: cover, illustration, poster, diagram-like visual, etc.
2. Decide the prompt language. Chinese prompts are fine and often preferred for the user's current workflow.
3. Pick an aspect ratio that matches the use case:
   - `1:1` for square social cards
   - `16:9` for covers and presentation visuals
   - `9:16` for mobile-first posters
   - `4:3` or `3:4` for article illustration variants
4. Run the script:

```bash
python /root/.openclaw-main/workspaces/writer/skills/runninghub-image/scripts/runninghub_text_to_image.py \
  --env-path /etc/openclaw/writer.env \
  --prompt "为 OpenClaw 多虾协同写一张科技感插画，五只拟人小龙虾在指挥中心协作，明亮、现代、可爱、带信息流光效" \
  --aspect-ratio 16:9 \
  --resolution 1k \
  --json
```

5. Read the JSON result and extract:
   - `taskId`
   - `status`
   - `imageUrl`
6. Reply with:
   - the final image URL
   - a one-line visual description
   - any useful prompt notes if the user may want a second iteration

## Environment

The script reads these values from env:

- `WRITER_IMAGE_API_KEY` or `RUNNINGHUB_API_KEY`
- `WRITER_IMAGE_API_BASE_URL` (default: `https://www.runninghub.cn/openapi/v2`)
- `WRITER_IMAGE_MODEL` (default: `rhart-image-n-g31-flash`)

Never print the API key back to the user.

## Failure handling

- If the API returns `FAILED`, report the failure reason briefly and offer a prompt retry.
- If polling times out, say the task is still running or timed out and include the `taskId`.
- If the image URL is missing, do not invent one.

## Good response shape

Use a short structure like:

```text
已完成生图
- 任务ID: ...
- 尺寸: 16:9 / 1k
- 图片链接: ...
- 画面说明: ...
```

## Notes

- Prefer `1k` for smoke tests and draft visuals to reduce latency and cost.
- Use more explicit visual style words when the user cares about personality or vibe.
- When the writer is generating article material, you can offer 1-2 alternate prompt directions after the first successful image.
