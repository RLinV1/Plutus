// Temporary visual check of the new FUNDAMENTALS/DIVIDENDS layout + MARKET view.
import { chromium } from "playwright-core";

const BASE = process.env.SMOKE_URL || "http://localhost:5173";
const browser = await chromium.launch({ channel: "msedge", headless: true });
const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();

await page.goto(BASE, { waitUntil: "domcontentloaded" });
// Dismiss the first-run tour if it pops.
try {
  await page.click("text=Skip", { timeout: 5000 });
} catch {}
await page.waitForSelector("text=FUNDAMENTALS", { timeout: 30000 });
await page.waitForTimeout(2500);
await page.screenshot({ path: "smoke-shots/check-research.png", fullPage: true });
await page.evaluate(() => {
  document.querySelector("main")?.scrollTo(0, 999999);
});
await page.waitForTimeout(500);
await page.screenshot({ path: "smoke-shots/check-research-bottom.png" });

await page.keyboard.press("2");
await page.waitForSelector("text=TODAY'S MOVERS", { timeout: 30000 });
await page.waitForTimeout(2000);
await page.screenshot({ path: "smoke-shots/check-market.png", fullPage: true });

await browser.close();
console.log("done");
