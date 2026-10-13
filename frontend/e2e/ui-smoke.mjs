// The real frontend against a real backend, in a real browser (Chromium via
// Playwright). CI runs it against hospital B; see .github/workflows/deploy.yml.
//
//   1. An administrator signs in through the login form. The session arrives as
//      an HttpOnly cookie: the page's own scripts cannot read it.
//   2. On Federation Peers they register a peer (secret shown once), rotate its
//      secret, suspend and reinstate it — and the backend agrees with the screen.
//   3. No request ever carries the token as a Bearer header; every state change
//      carries the CSRF header.
//   4. After logout the very same cookie is refused by the API.
//
// Env: UI_URL (default http://localhost:3000), API_URL (default http://localhost:8001),
//      UI_ADMIN_ID, UI_ADMIN_PASSWORD. Run it from a directory where `playwright` is installed.
import { chromium } from "playwright";

const UI = process.env.UI_URL || "http://localhost:3000";
const API = process.env.API_URL || "http://localhost:8001";
const ADMIN = process.env.UI_ADMIN_ID;
const PASSWORD = process.env.UI_ADMIN_PASSWORD;

let failures = 0;
const check = (ok, what) => {
  console.log(`${ok ? "ok  " : "FAIL"} ${what}`);
  if (!ok) failures += 1;
};

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();
  page.setDefaultTimeout(20_000);
  const apiRequests = [];
  page.on("request", (r) => {
    if (r.url().startsWith(API)) apiRequests.push({ method: r.method(), url: r.url(), headers: r.headers() });
  });
  page.on("dialog", (d) => d.accept());           // "Issue a new secret?" confirmations

  try {
    // ── 1. Sign in through the form ──────────────────────────────────────────
    await page.goto(`${UI}/login`);
    await page.fill('input[placeholder="PAT-2026-000001"]', ADMIN);
    await page.fill('input[type="password"]', PASSWORD);
    await page.press('input[type="password"]', "Enter");
    await page.waitForURL(/\/dashboard\/admin/);
    check(true, "administrator signed in through the login form");

    const apiCookies = await context.cookies(API);
    const session = apiCookies.find((c) => c.name === "quantumcare_token");
    check(Boolean(session && session.httpOnly), "the session is an HttpOnly cookie on the API's host");
    const readable = await page.evaluate(() => document.cookie);
    check(!readable.includes("quantumcare_token"), "page scripts cannot read the session token");

    // ── 2. Federation peers: register, rotate, suspend, reinstate ────────────
    const name = `ui-peer-${Date.now().toString(36)}`;
    await page.goto(`${UI}/dashboard/admin/federation`);
    await page.fill("#peer-name", name);
    await page.getByRole("button", { name: "Register" }).click();
    await page.getByText(`Shared secret for ${name}`).waitFor();
    const first = (await page.getByTestId("issued-secret").textContent()).trim();
    check(/^[0-9a-f]{64}$/.test(first), "registering shows a 64-hex secret once");

    const row = page.locator("div.p-5", { has: page.getByText(name, { exact: true }) });
    await row.getByRole("button", { name: "Rotate secret" }).click();
    await page.getByText(`New shared secret for ${name}`).waitFor();
    const second = (await page.getByTestId("issued-secret").textContent()).trim();
    check(/^[0-9a-f]{64}$/.test(second) && second !== first, "rotating issues a different secret");

    await row.getByRole("button", { name: "Suspend" }).click();
    await row.getByText("Suspended").waitFor();
    check(true, "suspending shows the peer as suspended");
    await row.getByRole("button", { name: "Reinstate" }).click();
    await row.getByText("Active").waitFor();

    // What the backend holds, asked with the browser's own session.
    const peers = await page.evaluate(async (api) => {
      const r = await fetch(`${api}/api/admin/federated/peers`, { credentials: "include" });
      return r.json();
    }, API);
    const peer = peers.peers.find((p) => p.node_name === name);
    check(Boolean(peer && peer.is_active && peer.secret_rotated_at), "the backend agrees: active, secret rotated");

    // ── 3. What the browser sent ─────────────────────────────────────────────
    check(apiRequests.length > 0 && apiRequests.every((r) => !r.headers.authorization),
      `no Bearer header on any of ${apiRequests.length} API requests`);
    const changes = apiRequests.filter((r) => r.method !== "GET" && !r.url.endsWith("/api/login"));
    check(changes.length >= 3 && changes.every((r) => r.headers["x-requested-with"] === "QuantumCare"),
      `the CSRF header on all ${changes.length} state-changing requests`);

    // ── 4. Logout revokes the session ────────────────────────────────────────
    await page.goto(`${UI}/dashboard/admin`);
    await page.getByRole("button", { name: /logout/i }).first().click();
    await page.waitForURL(/\/login|\/$/);
    const fresh = await browser.newContext();
    await fresh.addCookies([{ ...session }]);       // the same cookie, replayed
    const replay = await fresh.request.get(`${API}/api/auth/me`);
    check(replay.status() === 401, `the logged-out cookie, replayed, is refused (HTTP ${replay.status()})`);
    await fresh.close();
  } catch (error) {
    console.error(error);
    await page.screenshot({ path: "/tmp/ui-smoke-failure.png", fullPage: true }).catch(() => {});
    failures += 1;
  } finally {
    await browser.close();
  }
  if (failures) {
    console.error(`${failures} check(s) failed`);
    process.exit(1);
  }
  console.log("all browser checks passed");
})();
