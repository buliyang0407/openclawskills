import { getStoredToken, setStoredToken, removeStoredToken, tokenStatus } from "/root/.openclaw/extensions/feishu-openclaw-plugin/src/core/token-store.js";
import { resolveOAuthEndpoints } from "/root/.openclaw/extensions/feishu-openclaw-plugin/src/core/device-flow.js";

async function readStdin() {
  let input = "";
  for await (const chunk of process.stdin) {
    input += chunk;
  }
  return input.trim();
}

async function refreshToken(req, stored) {
  if (Date.now() >= Number(stored.refreshExpiresAt || 0)) {
    await removeStoredToken(req.appId, req.userOpenId);
    throw new Error("stored_user_token_expired");
  }
  const endpoints = resolveOAuthEndpoints(req.domain || "feishu");
  const body = new URLSearchParams({
    grant_type: "refresh_token",
    refresh_token: String(stored.refreshToken || ""),
    client_id: req.appId,
    client_secret: req.appSecret,
  }).toString();
  const resp = await fetch(endpoints.token, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  const data = await resp.json();
  const code = data.code;
  const error = data.error;
  if ((code !== undefined && code !== 0) || error) {
    if (code === 20003 || code === 20004 || code === 20024 || code === 20063) {
      await removeStoredToken(req.appId, req.userOpenId);
      throw new Error("stored_user_token_expired");
    }
    throw new Error(`refresh_failed:${code ?? error}:${data.error_description ?? data.msg ?? "unknown"}`);
  }
  if (!data.access_token) {
    throw new Error("refresh_missing_access_token");
  }
  const now = Date.now();
  const updated = {
    userOpenId: stored.userOpenId,
    appId: req.appId,
    accessToken: data.access_token,
    refreshToken: data.refresh_token ?? stored.refreshToken,
    expiresAt: now + Number(data.expires_in ?? 7200) * 1000,
    refreshExpiresAt: data.refresh_token_expires_in
      ? now + Number(data.refresh_token_expires_in) * 1000
      : stored.refreshExpiresAt,
    scope: data.scope ?? stored.scope,
    grantedAt: stored.grantedAt,
  };
  await setStoredToken(updated);
  return updated.accessToken;
}

async function getValidAccessToken(req) {
  const stored = await getStoredToken(req.appId, req.userOpenId);
  if (!stored) {
    throw new Error("missing_user_token");
  }
  const status = tokenStatus(stored);
  if (status === "valid") {
    return stored.accessToken;
  }
  if (status === "needs_refresh") {
    return refreshToken(req, stored);
  }
  await removeStoredToken(req.appId, req.userOpenId);
  throw new Error("stored_user_token_expired");
}

async function feishuJson(url, accessToken, init = {}) {
  const resp = await fetch(url, {
    ...init,
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json; charset=utf-8",
      ...(init.headers || {}),
    },
  });
  return await resp.json();
}

async function listTables(req, accessToken) {
  const data = await feishuJson(
    `https://open.feishu.cn/open-apis/bitable/v1/apps/${req.appToken}/tables?page_size=200`,
    accessToken,
  );
  if (data.code !== 0) {
    throw new Error(`list_tables_failed:${JSON.stringify(data)}`);
  }
  return data.data?.items || [];
}

async function createTable(req, accessToken) {
  if (!req.tableName) {
    throw new Error("bitable_requires_explicit_table_id");
  }
  const data = await feishuJson(
    `https://open.feishu.cn/open-apis/bitable/v1/apps/${req.appToken}/tables`,
    accessToken,
    {
      method: "POST",
      body: JSON.stringify({
        table: {
          name: String(req.tableName),
        },
      }),
    },
  );
  if (data.code !== 0) {
    throw new Error(`create_table_failed:${JSON.stringify(data)}`);
  }
  const tableId = data.data?.table_id || data.data?.table?.table_id || "";
  if (!tableId) {
    throw new Error(`create_table_missing_id:${JSON.stringify(data)}`);
  }
  return String(tableId);
}

async function createTableAction(req) {
  if (!req.tableName) {
    throw new Error("bitable_requires_explicit_table_id");
  }
  const accessToken = await getValidAccessToken(req);
  const tableId = await createTable(req, accessToken);
  return {
    ok: true,
    tableId,
    tableName: String(req.tableName),
  };
}

async function ensureTable(req, accessToken) {
  if (req.tableId) {
    return String(req.tableId);
  }
  const items = await listTables(req, accessToken);
  if (req.tableName) {
    const exact = items.find((item) => String(item.name || "") === String(req.tableName));
    if (exact?.table_id) {
      return String(exact.table_id);
    }
    return await createTable(req, accessToken);
  }
  if (items.length === 1 && items[0]?.table_id) {
    return String(items[0].table_id);
  }
  if (items.length === 0) {
    throw new Error("bitable_has_no_tables");
  }
  throw new Error("bitable_requires_explicit_table_id");
}

async function ensureFields(req, accessToken, tableId) {
  const fieldNames = Array.isArray(req.fieldNames) ? req.fieldNames.map((x) => String(x)) : [];
  if (fieldNames.length === 0) {
    return;
  }
  const data = await feishuJson(
    `https://open.feishu.cn/open-apis/bitable/v1/apps/${req.appToken}/tables/${tableId}/fields?page_size=500`,
    accessToken,
  );
  if (data.code !== 0) {
    throw new Error(`list_fields_failed:${JSON.stringify(data)}`);
  }
  const existing = new Set((data.data?.items || []).map((item) => String(item.field_name || "")));
  for (const fieldName of fieldNames) {
    if (existing.has(fieldName)) {
      continue;
    }
    const created = await feishuJson(
      `https://open.feishu.cn/open-apis/bitable/v1/apps/${req.appToken}/tables/${tableId}/fields`,
      accessToken,
      {
        method: "POST",
        body: JSON.stringify({
          field_name: fieldName,
          type: 1,
        }),
      },
    );
    if (created.code !== 0) {
      throw new Error(`create_field_failed:${fieldName}:${JSON.stringify(created)}`);
    }
  }
}

async function appendRecord(req) {
  const accessToken = await getValidAccessToken(req);
  const tableId = await ensureTable(req, accessToken);
  await ensureFields(req, accessToken, tableId);
  const data = await feishuJson(
    `https://open.feishu.cn/open-apis/bitable/v1/apps/${req.appToken}/tables/${tableId}/records`,
    accessToken,
    {
      method: "POST",
      body: JSON.stringify({
        fields: req.fields || {},
      }),
    },
  );
  if (data.code !== 0) {
    throw new Error(`append_record_failed:${JSON.stringify(data)}`);
  }
  return {
    ok: true,
    tableId,
    recordId: data.data?.record?.record_id || "",
  };
}

async function updateRecord(req) {
  if (!req.recordId) {
    throw new Error("bitable_requires_record_id");
  }
  const accessToken = await getValidAccessToken(req);
  const tableId = await ensureTable(req, accessToken);
  await ensureFields(req, accessToken, tableId);
  const data = await feishuJson(
    `https://open.feishu.cn/open-apis/bitable/v1/apps/${req.appToken}/tables/${tableId}/records/${req.recordId}`,
    accessToken,
    {
      method: "PUT",
      body: JSON.stringify({
        fields: req.fields || {},
      }),
    },
  );
  if (data.code !== 0) {
    throw new Error(`update_record_failed:${JSON.stringify(data)}`);
  }
  return {
    ok: true,
    tableId,
    recordId: data.data?.record?.record_id || String(req.recordId),
  };
}

async function listTablesAction(req) {
  const accessToken = await getValidAccessToken(req);
  const items = await listTables(req, accessToken);
  return {
    ok: true,
    items: items.map((item) => ({
      tableId: String(item.table_id || ""),
      name: String(item.name || ""),
      revision: Number(item.revision || 0),
    })),
  };
}

async function listRecordsAction(req) {
  const accessToken = await getValidAccessToken(req);
  const tableId = await ensureTable(req, accessToken);
  const pageSize = Math.min(Math.max(Number(req.pageSize || 100), 1), 500);
  const pageToken = String(req.pageToken || "");
  const url = new URL(
    `https://open.feishu.cn/open-apis/bitable/v1/apps/${req.appToken}/tables/${tableId}/records`,
  );
  url.searchParams.set("page_size", String(pageSize));
  if (pageToken) {
    url.searchParams.set("page_token", pageToken);
  }
  const data = await feishuJson(url.toString(), accessToken);
  if (data.code !== 0) {
    throw new Error(`list_records_failed:${JSON.stringify(data)}`);
  }
  return {
    ok: true,
    tableId,
    hasMore: Boolean(data.data?.has_more),
    pageToken: String(data.data?.page_token || ""),
    total: Number(data.data?.total || 0),
    items: (data.data?.items || []).map((item) => ({
      recordId: String(item.record_id || ""),
      fields: item.fields || {},
      createdTime: Number(item.created_time || 0),
      lastModifiedTime: Number(item.last_modified_time || 0),
    })),
  };
}

async function main() {
  const raw = await readStdin();
  if (!raw) {
    throw new Error("missing_request_payload");
  }
  const req = JSON.parse(raw);
  let result;
  if (req.action === "append_record") {
    result = await appendRecord(req);
  } else if (req.action === "update_record") {
    result = await updateRecord(req);
  } else if (req.action === "list_tables") {
    result = await listTablesAction(req);
  } else if (req.action === "create_table") {
    result = await createTableAction(req);
  } else if (req.action === "list_records") {
    result = await listRecordsAction(req);
  } else {
    throw new Error(`unsupported_action:${req.action || ""}`);
  }
  process.stdout.write(JSON.stringify(result));
}

main().catch((err) => {
  process.stderr.write(String(err?.message || err));
  process.exit(1);
});
