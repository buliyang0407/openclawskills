---
name: feishu-cloud-doc
description: Use this skill whenever the writer should turn content into a real Feishu cloud document instead of only returning plain chat text. This applies to formal drafts, briefings, long-form articles, summaries, working notes, project docs, and any request like “生成飞书文档”, “写成云文档”, “发到飞书里”, “给我一个可继续编辑的版本”, or “把这份内容落成文档”.
---

# Feishu Cloud Doc

Use this skill when the user wants editable output in Feishu Docs, not only a chat reply.

The goal is not just “call a tool once”, but to leave the user with a real, readable, editable Feishu document and a reliable result message.

## Tools to use

Prefer these existing Feishu OpenClaw tools:

- `feishu_create_doc`
- `feishu_update_doc`
- `feishu_fetch_doc`
- `feishu_wiki_space`
- `feishu_wiki_space_node`

Do not build a parallel raw API flow unless these tools are unavailable.

## Core principles

1. Draft first, write second.
2. Prefer the main create-doc path when creating a new doc.
3. If the main path fails for a known platform reason, switch to the fallback path instead of getting stuck.
4. After creating or updating a doc, verify the content landed when practical.
5. Never claim success unless you have either:
   - a working doc link or token
   - or a verified task id that can be queried later

## Decision tree

### Case A: The user wants a new doc

Use `feishu_create_doc` first.

Provide:

- `title`
- `markdown`
- destination hint when available:
  - `folder_token`
  - or `wiki_node`
  - or `wiki_space`

If the user does not specify a destination, use the default live destination behavior. If a wiki-space hint is needed, `my_library` is a sensible default.

### Case B: The user gives an existing doc URL or token

Use `feishu_update_doc`.

Typical modes:

- `overwrite`: replace the entire document
- `append`: add content to the end
- `replace_all`: global replacement
- `replace_range` / `insert_before` / `insert_after`: precise edits when the user references a section

### Case C: The user wants to inspect or verify an existing doc

Use `feishu_fetch_doc`.

This is especially helpful after create/update operations, or when the user says “看看有没有写进去”.

## Primary workflow

Use this workflow for most “new doc” tasks:

1. Finalize the markdown body.
2. Infer or confirm a doc title.
3. Call `feishu_create_doc`.
4. Capture the useful result fields:
   - `obj_token`
   - `url`
   - `task_id` if the tool returns one
5. If creation succeeds, optionally call `feishu_fetch_doc` for a short sanity check when the task is important or when the system has been flaky recently.
6. Reply with a concise result summary.

## Fallback workflow

Use the fallback path if `feishu_create_doc` is blocked by a known Feishu-side issue, especially:

- missing `docs:document.media:upload`
- `need_user_authorization`
- repeated create-doc failures while wiki/docx operations still work

Fallback steps:

1. List wiki spaces with `feishu_wiki_space` and choose a writable space.
2. Create a new `docx` node with `feishu_wiki_space_node`:
   - `action=create`
   - `obj_type=docx`
   - `space_id=<chosen space>`
   - `title=<doc title>`
3. Capture:
   - `node_token`
   - `obj_token`
4. Call `feishu_update_doc` with:
   - `doc_id=<obj_token>`
   - `mode=overwrite`
   - `markdown=<final content>`
5. Use `feishu_fetch_doc` to confirm the body landed if the write matters.
6. Return the final doc link using the `obj_token`.

## Verification rule

When a doc is newly created or heavily updated, prefer to verify by fetching it back unless:

- the platform response is already clearly complete and trustworthy
- the user wants speed over certainty

Minimum verification standard:

- title looks correct
- body is not empty
- key headings or bullet points are present

## Content guidance

Before writing the doc:

- clean away obvious chat-only phrasing
- preserve headings and bullet structure
- keep markdown simple and Feishu-friendly
- avoid dumping raw JSON unless the user explicitly asked for it
- infer a practical title if the user did not provide one

## Failure handling

### If `feishu_create_doc` fails with scope or auth errors

Do not loop on the same failing call.

Choose one of these:

1. switch to the fallback workflow if the task is simply “create a doc”
2. if the failure clearly says user authorization is required and fallback is also unlikely to work, tell the user to run `/feishu auth`

### If `feishu_update_doc` fails

- do not claim the original doc was changed
- return the markdown body as a fallback if the user still needs the content immediately

### If the tool returns an async `task_id`

- query or re-check before claiming the document is ready

## Output format

Prefer this short result shape:

```text
已生成飞书云文档
- 标题: ...
- 文档链接: ...
- obj_token: ...
- 说明: ...
```

If fallback was used, mention that briefly:

```text
已生成飞书云文档（备用链路）
```

If only `node_token` is available, return it too.

## Good examples

### Example 1: New formal doc

User request:

```text
把这份简报整理成飞书文档，方便我继续改
```

Recommended action:

- draft clean markdown
- call `feishu_create_doc`
- verify with `feishu_fetch_doc` if needed
- return link + token

### Example 2: Update an existing doc

User request:

```text
把这个飞书文档里的结论部分改成新版
```

Recommended action:

- extract the doc id from URL or token
- use `feishu_update_doc`
- choose `replace_range` / `replace_all` / `overwrite` appropriately

### Example 3: Known create-doc trouble

User request:

```text
给我生成一份飞书文档
```

If `feishu_create_doc` fails with known auth or scope issues:

- switch to wiki `docx` create
- overwrite content with `feishu_update_doc`
- fetch back to confirm

## Writer-specific use

This skill pairs naturally with:

- `doc-coauthoring` for structured drafting
- `internal-comms` for formal internal updates
- `wechat-article-writer` for article drafts that should land in Feishu
- `voice-editor` for polishing before final doc creation

## Practical note for this environment

In the current OpenClaw production environment, both of these have been observed in real runs:

- the main `feishu_create_doc` path can succeed after permissions and auth are aligned
- the wiki `docx` fallback path is also viable

So the right behavior is:

- try the main path first for a normal new-doc request
- fail over quickly when the platform tells you to
- verify the final result instead of arguing with the platform
