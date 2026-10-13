// Checks the consent-token vault (src/lib/tokenVault.ts) with Node's WebCrypto,
// the same SubtleCrypto API the browser uses. Run: node scripts/check-vault.mjs
import {
  sealToken, openToken, openTokenWithPasskey, isSealed, isPasskeySealed, isPassphraseSealed,
  passkeySupported, protectedBy, VaultError,
} from "../src/lib/tokenVault.ts";

const check = (ok, what) => { if (!ok) { console.error("FAIL:", what); process.exit(1); } console.log("ok  ", what); };
const rejects = async (promise) => { try { await promise; return false; } catch (e) { return e instanceof VaultError; } };

const token = "mlwe1:" + "ab".repeat(48);
const sealed = await sealToken(token, "correct horse battery", "patient-1");

check(isSealed(sealed), "a sealed token has the expected shape");
check(!JSON.stringify(sealed).includes(token) && !JSON.stringify(sealed).includes("abab"),
  "the stored form does not contain the token");
check(await openToken(sealed, "correct horse battery", "patient-1") === token, "the right passphrase opens it");
check(await rejects(openToken(sealed, "wrong horse battery", "patient-1")), "a wrong passphrase is refused");
check(await rejects(openToken(sealed, "correct horse battery", "patient-2")),
  "it will not open as another patient's token");
const flipped = { ...sealed, ct: (sealed.ct[0] === "A" ? "B" : "A") + sealed.ct.slice(1) };
check(await rejects(openToken(flipped, "correct horse battery", "patient-1")), "a tampered ciphertext is refused");
check(await rejects(sealToken(token, "short", "patient-1")), "a passphrase under 8 characters is refused");
const again = await sealToken(token, "correct horse battery", "patient-1");
check(again.salt !== sealed.salt && again.ct !== sealed.ct, "each seal uses a fresh salt and IV");

// ─── Passkey-sealed tokens ───────────────────────────────────────────────────
// Creating one needs an authenticator, so that path is exercised in the browser
// (frontend/e2e/ui-smoke.mjs, with a virtual authenticator). What is checked
// here is everything around it: the shapes are told apart, and neither kind of
// sealed token can be opened by the other's method.
const passkeySealed = { v: 1, kdf: "WebAuthn-PRF", credentialId: "Y3JlZC1pZA",
                        salt: sealed.salt, iv: sealed.iv, ct: sealed.ct };

check(isPasskeySealed(passkeySealed) && isSealed(passkeySealed), "a passkey-sealed token is recognised");
check(!isPassphraseSealed(passkeySealed), "it is not mistaken for a passphrase-sealed one");
check(!isPasskeySealed(sealed) && isPassphraseSealed(sealed), "and the passphrase-sealed one is not mistaken for it");
check(protectedBy(passkeySealed) === "passkey" && protectedBy(sealed) === "passphrase",
  "each says how it is protected");
check(!isPasskeySealed({ ...passkeySealed, credentialId: "" }), "one naming no credential is refused");
check(await rejects(openToken(passkeySealed, "correct horse battery", "patient-1")),
  "a passkey-sealed token will not open with a passphrase");
check(await rejects(openTokenWithPasskey(sealed, "patient-1")),
  "a passphrase-sealed token will not open with a passkey");
check(await passkeySupported() === false, "no passkey is claimed where there is no authenticator (Node)");
