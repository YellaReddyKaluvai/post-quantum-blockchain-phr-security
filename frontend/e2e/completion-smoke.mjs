// Real browser + backend checks. Run after ui-smoke against disposable CI users.
import { chromium } from "playwright";
import { createHmac } from "node:crypto";
const origin = process.env.UI_ORIGIN || "http://localhost:3000";
const password = process.env.UI_ADMIN_PASSWORD;
if (!password) throw new Error("UI_ADMIN_PASSWORD is required");
function otp(secret) {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const c of secret.replace(/=/g, ""))
    bits += alphabet.indexOf(c).toString(2).padStart(5, "0");
  const key = Buffer.from(bits.match(/.{8}/g).map((x) => parseInt(x, 2)));
  const msg = Buffer.alloc(8);
  msg.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000)));
  const hash = createHmac("sha1", key).update(msg).digest();
  const offset = hash[19] & 15;
  return String((hash.readUInt32BE(offset) & 0x7fffffff) % 1000000).padStart(
    6,
    "0",
  );
}
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
try {
  await page.goto(origin + "/login");
  await page.locator("#login-id").fill(process.env.UI_ADMIN_ID);
  await page.locator("#login-password").fill(password);
  await page.getByRole("button", { name: "Authenticate Portal" }).click();
  await page.waitForURL("**/dashboard/admin");
  const cookie = (await page.context().cookies()).find(
    (c) => c.name === "quantumcare_token",
  );
  if (!cookie) throw new Error("Missing access cookie");
  await page
    .context()
    .addCookies([{ ...cookie, value: "expired-test-session" }]);
  await page.goto(origin + "/dashboard/account");
  await page.getByLabel("Current password", { exact: true }).fill(password);
  await page
    .getByRole("button", { name: "Set up authenticator", exact: true })
    .click();
  const secret = await page.locator("code").innerText();
  await page.getByAltText("Authenticator setup QR code").waitFor();
  await page.getByLabel("Six-digit code").fill(otp(secret));
  await page.getByRole("button", { name: "Enable MFA", exact: true }).click();
  await page
    .getByText("10 recovery codes remaining.", { exact: true })
    .waitFor();
  let codes = (await page.locator("pre").innerText()).trim().split(/\s+/);
  await page.getByLabel("Current password", { exact: true }).fill(password);
  await page
    .getByLabel("Authenticator / recovery code", { exact: true })
    .fill(codes[0]);
  page.once("dialog", (d) => d.accept());
  await page
    .getByRole("button", { name: "Generate new recovery codes" })
    .click();
  await page
    .getByText(/Previous recovery codes have been invalidated/)
    .waitFor();
  codes = (await page.locator("pre").innerText()).trim().split(/\s+/);
  await page.getByLabel("Current password", { exact: true }).fill(password);
  await page
    .getByLabel("Authenticator / recovery code", { exact: true })
    .fill(codes[0]);
  await page.getByRole("button", { name: "Rotate keys", exact: true }).click();
  await page.getByText(/New keys are active/).waitFor();
  await page.getByLabel("Current password", { exact: true }).fill(password);
  await page
    .getByLabel("Authenticator / recovery code", { exact: true })
    .fill(codes[1]);
  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "Disable MFA", exact: true }).click();
  await page.getByText("MFA disabled.", { exact: true }).waitFor();
  // Invalid recovery links must surface a real API error, not success.
  await page.goto(origin + "/reset-password#token=" + "invalid".repeat(8));
  await page
    .getByLabel("New password (12+ characters)")
    .fill("Disposable-Test-Password-123!");
  await page
    .getByLabel("Confirm password", { exact: true })
    .fill("Disposable-Test-Password-123!");
  await page
    .getByRole("button", { name: "Reset password", exact: true })
    .click();
  await page
    .getByRole("alert")
    .filter({ hasText: /invalid|expired/i })
    .waitFor();
  // Doctor schedule editor against the actual API.
  await page.context().clearCookies();
  await page.goto(origin + "/login");
  await page.locator("#login-id").fill(process.env.UI_DOCTOR_ID);
  await page.locator("#login-password").fill(password);
  await page.getByRole("button", { name: "Authenticate Portal" }).click();
  await page.waitForURL("**/dashboard/doctor");
  await page.goto(origin + "/dashboard/doctor/appointments");
  await page
    .getByText("Manage working hours and leave", { exact: true })
    .click();
  await page.getByLabel("Appointment duration", { exact: true }).fill("45");
  await page.getByRole("button", { name: "Save availability" }).click();
  await page
    .getByRole("status")
    .filter({ hasText: /Availability saved/ })
    .waitFor();
  console.log(
    "Completion browser flows passed: expired-session refresh, MFA, recovery codes, PQC rotation, invalid reset, doctor availability.",
  );
} finally {
  await browser.close();
}
