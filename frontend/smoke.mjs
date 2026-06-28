// Headless smoke-drive of the terminal UI via preinstalled Edge.
// Usage: node smoke.mjs   (dev server on :5173, backend on :8000)
import { chromium } from "playwright-core";
import { mkdirSync } from "node:fs";

const OUT = "smoke-shots";
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch({ channel: "msedge", headless: true });
const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
const errors = [];
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
page.on("pageerror", (e) => errors.push(String(e)));

await page.goto(process.env.SMOKE_URL || "http://localhost:5173", { waitUntil: "domcontentloaded" });

// 1) RESEARCH view: wait for the candle chart canvas + quote panel.
await page.waitForSelector("text=QUOTE · AAPL", { timeout: 30000 });
await page.waitForSelector("canvas", { timeout: 30000 });
await page.waitForTimeout(1200);
await page.screenshot({ path: `${OUT}/1-research.png` });

// 2) MARKET view (indices + VIX + movers).
await page.keyboard.press("2");
await page.waitForSelector("text=TODAY'S MOVERS", { timeout: 30000 });
await page.waitForTimeout(1200);
await page.screenshot({ path: `${OUT}/2-market.png`, fullPage: true });

// 3) PORTFOLIO view (keyboard nav — single-key view switching). The equity
// curve only renders when the portfolio has holdings; accept the empty state.
await page.keyboard.press("3");
await page.waitForSelector(
  "text=/EQUITY CURVE|No holdings yet/",
  { timeout: 30000 },
);
await page.waitForTimeout(1500);
await page.screenshot({ path: `${OUT}/3-portfolio.png`, fullPage: true });

// 4) SCENARIO LAB.
await page.keyboard.press("5");
await page.waitForSelector("text=ESTIMATED IMPACT", { timeout: 30000 });
await page.waitForTimeout(800);
await page.screenshot({ path: `${OUT}/4-scenario.png`, fullPage: true });

// 5) Command palette.
await page.keyboard.press("Control+k");
await page.waitForSelector("[cmdk-dialog]", { timeout: 10000 });
await page.keyboard.type("NV");
await page.waitForTimeout(500);
await page.screenshot({ path: `${OUT}/5-palette.png` });
await page.keyboard.press("Escape");

// 6) Alerts view (notifications from the live loop).
await page.keyboard.press("6");
await page.waitForSelector("text=ARMED RULES", { timeout: 15000 });
await page.waitForTimeout(800);
await page.screenshot({ path: `${OUT}/6-alerts.png` });

// 7) Floating advisor chat bubble (bottom-right).
await page.keyboard.press("1");
await page.waitForSelector("text=QUOTE", { timeout: 15000 });
await page.click('button[aria-label="Open advisor chat"]');
await page.waitForSelector("text=Ask about any stock", { timeout: 10000 });
await page.screenshot({ path: `${OUT}/7-chat-widget.png` });

console.log("console errors:", errors.length ? errors : "none");
await browser.close();
