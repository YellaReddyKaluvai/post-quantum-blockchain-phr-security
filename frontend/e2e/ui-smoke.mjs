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
//   5. A doctor protects a consent token with a passkey — a virtual authenticator
//      standing in for Touch ID — and proves consent with it. What is stored is
//      ciphertext under a key the authenticator holds: no passphrase is typed,
//      and the token itself is nowhere in browser storage.
//
// Env: UI_URL (default http://localhost:3000), API_URL (default http://localhost:8001),
//      UI_ADMIN_ID, UI_ADMIN_PASSWORD, UI_DOCTOR_ID, UI_PATIENT_UUIDS (three, comma-separated).
//      Run it from a directory where `playwright` is installed.
import { chromium } from "playwright";

const UI = process.env.UI_URL || "http://localhost:3000";
const API = process.env.API_URL || "http://localhost:8001";
const ADMIN = process.env.UI_ADMIN_ID;
const PASSWORD = process.env.UI_ADMIN_PASSWORD;
const DOCTOR = process.env.UI_DOCTOR_ID;
// One patient per scenario: a consent token is delivered once and only once, so
// a scenario that collects one cannot reuse another's.
const PATIENTS = (process.env.UI_PATIENT_UUIDS || "").split(",").filter(Boolean);

let failures = 0;
const check = (ok, what) => {
  console.log(`${ok ? "ok  " : "FAIL"} ${what}`);
  if (!ok) failures += 1;
};

/**
 * The doctor's consent token, sealed by an authenticator rather than a typed
 * passphrase. Chrome's virtual authenticator stands in for the hardware; the
 * WebAuthn PRF extension is what yields the key, so if this build of Chromium
 * cannot offer PRF the checks say so instead of passing quietly.
 */
async function signInAsDoctor(page, patientId) {
  await page.goto(`${UI}/login`);
  await page.fill('input[placeholder="PAT-2026-000001"]', DOCTOR);
  await page.fill('input[type="password"]', PASSWORD);
  await page.press('input[type="password"]', "Enter");
  await page.waitForURL(/\/dashboard\/doctor/);
  await page.goto(`${UI}/dashboard/doctor/patients/${patientId}`);
}

async function passkeyChecks(browser) {
  const context = await browser.newContext();
  const page = await context.newPage();
  page.setDefaultTimeout(20_000);
  const cdp = await context.newCDPSession(page);
  await cdp.send("WebAuthn.enable");
  let authenticator;
  try {
    ({ authenticatorId: authenticator } = await cdp.send("WebAuthn.addVirtualAuthenticator", {
      options: {
        protocol: "ctap2", ctap2Version: "ctap2_1", transport: "internal",
        hasResidentKey: true, hasUserVerification: true, hasPrf: true,
        isUserVerified: true, automaticPresenceSimulation: true,
      },
    }));
  } catch (error) {
    console.log(`FAIL this Chromium cannot provide a PRF-capable authenticator: ${error.message}`);
    failures += 1;
    await context.close();
    return;
  }

  try {
    await signInAsDoctor(page, PATIENTS[0]);
    const passkeyOption = page.getByTestId("protect-with-passkey");
    await passkeyOption.waitFor();
    check(true, "the passkey option is offered where the device has an authenticator");
    await passkeyOption.click();
    await page.getByRole("button", { name: "Collect consent token" }).click();

    const protection = page.getByTestId("token-protection");
    await protection.waitFor();
    check((await protection.textContent()).includes("protected by a passkey"),
      "the token is sealed by the passkey, not a passphrase");

    const stored = await page.evaluate(() => {
      const key = Object.keys(localStorage).find((k) => k.startsWith("quantumcare.zkp."));
      return JSON.parse(localStorage.getItem(key));
    });
    check(stored.sealed && stored.sealed.kdf === "WebAuthn-PRF" && stored.sealed.credentialId.length > 0,
      "what is stored names the authenticator credential, not a passphrase KDF");
    check(!("token" in stored) && !JSON.stringify(stored).includes("mlwe1:" + "0".repeat(8)),
      "the token itself is not in browser storage");

    // Reload: the key is gone from memory and must come back from the authenticator.
    await page.reload();
    await page.getByRole("button", { name: "Prove consent" }).click();
    await page.getByText("Consent proven").waitFor();
    check(true, "after a reload the authenticator unlocks it and the proof verifies");

    // Without the authenticator the token cannot be opened at all.
    await cdp.send("WebAuthn.removeVirtualAuthenticator", { authenticatorId: authenticator });
    await page.reload();
    await page.getByRole("button", { name: "Prove consent" }).click();
    // Nothing to answer the prompt: the proof cannot complete, and the token
    // stays sealed. (The browser waits out its own WebAuthn timeout.)
    await page.waitForTimeout(5_000);
    check(!(await page.getByText("Consent proven").isVisible()),
      "with the authenticator gone the token stays sealed");

    // An authenticator that cannot hold a key: said plainly, before anything is stored.
    const plain = await browser.newContext();
    const plainPage = await plain.newPage();
    plainPage.setDefaultTimeout(20_000);
    const plainCdp = await plain.newCDPSession(plainPage);
    await plainCdp.send("WebAuthn.enable");
    await plainCdp.send("WebAuthn.addVirtualAuthenticator", { options: {
      protocol: "ctap2", transport: "internal", hasResidentKey: true, hasUserVerification: true,
      isUserVerified: true, automaticPresenceSimulation: true } });          // no PRF
    await signInAsDoctor(plainPage, PATIENTS[1]);
    await plainPage.getByTestId("protect-with-passkey").click();
    await plainPage.getByRole("button", { name: "Collect consent token" }).click();
    const refusal = plainPage.locator("p[role=alert]");
    await refusal.waitFor();
    check((await refusal.textContent()).includes("passphrase"),
      "an authenticator that cannot hold a key says so and points to a passphrase");
    check(await plainPage.evaluate(
      () => Object.keys(localStorage).filter((k) => k.startsWith("quantumcare.zkp.")).length === 0),
      "and nothing half-protected is stored");

    // The passphrase path is untouched by any of this — on a third consent,
    // since the second scenario's token was never collected but this one is.
    await signInAsDoctor(plainPage, PATIENTS[2]);
    await plainPage.getByTestId("protect-with-passphrase").click();
    await plainPage.fill("#zkp-pass", "fallback-phrase");
    await plainPage.fill("#zkp-pass2", "fallback-phrase");
    await plainPage.getByRole("button", { name: "Collect consent token" }).click();
    await plainPage.getByTestId("token-protection").waitFor();
    check((await plainPage.getByTestId("token-protection").textContent()).includes("under a passphrase"),
      "choosing a passphrase still protects the token");
    await plainPage.reload();
    await plainPage.fill("#zkp-unlock", "fallback-phrase");
    await plainPage.getByRole("button", { name: "Prove consent" }).click();
    await plainPage.getByText("Consent proven").waitFor();
    check(true, "and the passphrase still proves consent");
    await plain.close();
  } catch (error) {
    console.error(error);
    await page.screenshot({ path: "/tmp/ui-smoke-passkey-failure.png", fullPage: true }).catch(() => {});
    failures += 1;
  } finally {
    await context.close();
  }
}

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
    // ── 5. A consent token protected by a passkey ────────────────────────────
    if (DOCTOR && PATIENTS.length >= 3) await passkeyChecks(browser);
    else console.log("skip  passkey checks (UI_DOCTOR_ID / three UI_PATIENT_UUIDS not set)");
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
