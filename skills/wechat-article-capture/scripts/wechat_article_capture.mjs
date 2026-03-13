#!/usr/bin/env node
import { chromium } from "playwright";

function getArg(name, fallback = "") {
  const index = process.argv.indexOf(name);
  if (index === -1 || index + 1 >= process.argv.length) {
    return fallback;
  }
  return process.argv[index + 1];
}

function hasFlag(name) {
  return process.argv.includes(name);
}

function cleanText(value) {
  return String(value || "").replace(/\u00a0/g, " ").replace(/\s+/g, " ").trim();
}

const url = getArg("--url");
const timeoutMs = Math.max(Number(getArg("--timeout-ms", "45000")) || 45000, 5000);
const headed = hasFlag("--headed");
const jsonOnly = hasFlag("--json");
const browserChannel = getArg("--channel", "");

if (!url) {
  process.stderr.write("missing --url");
  process.exit(2);
}

async function main() {
  const browser = await chromium.launch({
    headless: !headed,
    channel: browserChannel || undefined,
    args: [
      "--disable-blink-features=AutomationControlled",
      "--disable-dev-shm-usage",
      "--no-default-browser-check",
      "--disable-features=IsolateOrigins,site-per-process",
    ],
  });
  const context = await browser.newContext({
    locale: "zh-CN",
    timezoneId: "Asia/Shanghai",
    viewport: { width: 1400, height: 2200 },
    userAgent:
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
      "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
  });
  await context.addInitScript(() => {
    Object.defineProperty(navigator, "webdriver", {
      get: () => undefined,
    });
    Object.defineProperty(navigator, "languages", {
      get: () => ["zh-CN", "zh", "en-US", "en"],
    });
    Object.defineProperty(navigator, "plugins", {
      get: () => [1, 2, 3, 4, 5],
    });
    window.chrome = window.chrome || { runtime: {} };
  });
  const page = await context.newPage();
  try {
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: timeoutMs });
    try {
      await page.waitForSelector("#js_content", { timeout: 12000 });
    } catch {}
    await page.waitForTimeout(2500);
    const payload = await page.evaluate(() => {
      const html = document.documentElement.outerHTML;
      const bodyText = document.body ? document.body.innerText || "" : "";
      const riskMarkers = [
        "环境异常",
        "访问过于频繁",
        "请在微信客户端打开链接",
        "去验证",
        "链接已过期",
        "内容已被发布者删除",
        "此内容因违规无法查看",
      ];
      const riskMarker = riskMarkers.find((marker) => bodyText.includes(marker)) || "";
      const hasContent = Boolean(document.querySelector("#js_content"));
      const titleNode =
        document.querySelector("#activity-name") ||
        document.querySelector(".rich_media_title") ||
        document.querySelector("meta[property='og:title']");
      const accountNode =
        document.querySelector("#js_name") ||
        document.querySelector(".profile_nickname") ||
        document.querySelector(".wx_follow_nickname");
      const aliasNode = document.querySelector("#js_profile_qrcode > strong");
      const authorNode =
        document.querySelector("#js_author_name") ||
        document.querySelector("meta[name='author']");
      const publishNode =
        document.querySelector("#publish_time") ||
        document.querySelector("#post-date");
      const contentNode = document.querySelector("#js_content");
      const coverNode =
        document.querySelector("meta[property='og:image']") ||
        document.querySelector("meta[name='twitter:image']");
      const descNode =
        document.querySelector("meta[property='og:description']") ||
        document.querySelector("meta[name='description']");

      const matchPublishTime = (sourceHtml) => {
        const patterns = [
          /create_time\s*:\s*JsDecode\('([^']+)'\)/,
          /create_time\s*[:=]\s*["']?(\d{10})["']?/,
          /d\.ct\s*=\s*["']?(\d{10})["']?/,
        ];
        for (const pattern of patterns) {
          const matched = sourceHtml.match(pattern);
          if (matched && matched[1]) {
            const raw = matched[1];
            const seconds = Number(raw);
            if (Number.isFinite(seconds) && seconds > 0) {
              const date = new Date(seconds * 1000);
              const pad = (num) => String(num).padStart(2, "0");
              return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
                `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
            }
            return raw;
          }
        }
        return "";
      };

      const clean = (value) => String(value || "").replace(/\u00a0/g, " ").replace(/\s+/g, " ").trim();
      const title =
        titleNode?.getAttribute?.("content") ||
        titleNode?.textContent ||
        document.title ||
        "";
      const accountName = accountNode?.textContent || "";
      const accountAlias = aliasNode?.textContent || "";
      const author =
        authorNode?.getAttribute?.("content") ||
        authorNode?.textContent ||
        "";
      const publishedAt = clean(publishNode?.textContent || "") || matchPublishTime(html);
      const bodyHtml = contentNode ? contentNode.innerHTML : "";
      const contentText = clean(contentNode?.innerText || "");
      const description =
        descNode?.getAttribute?.("content") ||
        clean(contentText).slice(0, 220);
      const coverImage = coverNode?.getAttribute?.("content") || "";
      const excerpt = clean(contentText).slice(0, 1200);
      return {
        ok: hasContent && !riskMarker && Boolean(clean(title)) && Boolean(clean(contentText)),
        url: location.href,
        title: clean(title),
        accountName: clean(accountName),
        accountAlias: clean(accountAlias),
        author: clean(author),
        publishedAt: clean(publishedAt),
        description: clean(description),
        coverImage: clean(coverImage),
        excerpt,
        contentText,
        bodyHtml,
        pageTitle: clean(document.title || ""),
        riskMarker,
        hasContent,
        wordCount: clean(contentText).length,
      };
    });
    if (jsonOnly) {
      process.stdout.write(JSON.stringify(payload, null, 2));
    } else {
      process.stdout.write(JSON.stringify(payload));
    }
    await browser.close();
    if (!payload.ok) {
      process.exit(1);
    }
  } catch (error) {
    await browser.close();
    const payload = {
      ok: false,
      url,
      error: String(error?.message || error),
    };
    if (jsonOnly) {
      process.stdout.write(JSON.stringify(payload, null, 2));
    } else {
      process.stdout.write(JSON.stringify(payload));
    }
    process.exit(1);
  }
}

main();
