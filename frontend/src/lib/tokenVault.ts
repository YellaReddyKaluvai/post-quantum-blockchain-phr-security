// Protection for a consent token kept in the browser (spec §17).
//
// The consent token is the doctor's private ZKP witness: whoever holds it can
// prove the patient's consent. Kept in localStorage as plain text, any script
// on this origin — or anyone with the disk or a stray backup file — could take
// it. What is stored here is AES-256-GCM ciphertext, under a key the page
// itself never holds for longer than one unlock. Two ways to get that key:
//
//   passkey    (preferred) the key comes out of an authenticator — Touch ID,
//              Windows Hello, a security key — through the WebAuthn PRF
//              extension. Nothing secret is ever typed, so a script injected
//              into this page has no keystrokes to steal and cannot derive the
//              key without the device and the user's touch.
//   passphrase (fallback)  PBKDF2-SHA-256 over a passphrase the doctor types.
//              Protects the token at rest; a script running at the moment the
//              passphrase is typed could still capture it.
//
// Passkeys are offered when the browser supports the PRF extension and a
// platform authenticator is present; otherwise the passphrase path is used, and
// the UI says which one protects the token. WebCrypto and WebAuthn only — no
// dependency, and the key never leaves SubtleCrypto.

export const VAULT_VERSION = 1;
export const KDF_ITERATIONS = 310_000;     // OWASP's PBKDF2-HMAC-SHA256 recommendation
export const MIN_PASSPHRASE_LENGTH = 8;
export const RP_NAME = "QuantumCare consent tokens";
// How long to wait for a touch before giving up. Without it, a prompt that is
// never answered — or an authenticator that is simply absent — leaves the page
// waiting with nothing to show for it.
export const WEBAUTHN_TIMEOUT_MS = 60_000;

interface SealedCommon {
  v: number;
  iv: string;     // base64, 12 bytes
  ct: string;     // base64, AES-256-GCM ciphertext + tag
  salt: string;   // base64, 16 bytes: the PBKDF2 salt, or the PRF input
}

export interface PassphraseSealed extends SealedCommon {
  kdf: "PBKDF2-SHA256";
  iterations: number;
}

export interface PasskeySealed extends SealedCommon {
  kdf: "WebAuthn-PRF";
  credentialId: string;   // base64url, which authenticator credential holds the key
}

export type SealedToken = PassphraseSealed | PasskeySealed;

export class VaultError extends Error {}

const b64 = (bytes: Uint8Array) => btoa(String.fromCharCode(...bytes));
const unb64 = (text: string) => Uint8Array.from(atob(text), (c) => c.charCodeAt(0));
const b64url = (bytes: Uint8Array) => b64(bytes).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const unb64url = (text: string) =>
  unb64(text.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (text.length % 4)) % 4));

/** Encrypt under ``key``, binding ``context`` (the patient ID) as associated data. */
async function encrypt(key: CryptoKey, token: string, context: string, iv: Uint8Array) {
  return new Uint8Array(await crypto.subtle.encrypt(
    { name: "AES-GCM", iv: iv as BufferSource, additionalData: new TextEncoder().encode(context) },
    key, new TextEncoder().encode(token)));
}

async function decrypt(key: CryptoKey, sealed: SealedToken, context: string): Promise<string> {
  const plain = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: unb64(sealed.iv) as BufferSource,
      additionalData: new TextEncoder().encode(context) },
    key, unb64(sealed.ct) as BufferSource);
  return new TextDecoder().decode(plain);
}

// ─── Passphrase ──────────────────────────────────────────────────────────────

async function deriveKey(passphrase: string, salt: Uint8Array, iterations: number): Promise<CryptoKey> {
  const material = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(passphrase), "PBKDF2", false, ["deriveKey"]);
  return crypto.subtle.deriveKey(
    { name: "PBKDF2", hash: "SHA-256", salt: salt as BufferSource, iterations },
    material, { name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]);
}

/** Encrypt ``token`` under ``passphrase``. */
export async function sealToken(token: string, passphrase: string, context: string): Promise<PassphraseSealed> {
  if (passphrase.length < MIN_PASSPHRASE_LENGTH) {
    throw new VaultError(`Use a passphrase of at least ${MIN_PASSPHRASE_LENGTH} characters.`);
  }
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const key = await deriveKey(passphrase, salt, KDF_ITERATIONS);
  return { v: VAULT_VERSION, kdf: "PBKDF2-SHA256", iterations: KDF_ITERATIONS,
           salt: b64(salt), iv: b64(iv), ct: b64(await encrypt(key, token, context, iv)) };
}

/** Decrypt; a wrong passphrase, a different context or any tampering fails the same way. */
export async function openToken(sealed: SealedToken, passphrase: string, context: string): Promise<string> {
  if (!isPassphraseSealed(sealed)) throw new VaultError("This token is protected by a passkey, not a passphrase.");
  try {
    return await decrypt(await deriveKey(passphrase, unb64(sealed.salt), sealed.iterations), sealed, context);
  } catch {
    throw new VaultError("Wrong passphrase, or the stored token was altered.");
  }
}

// ─── Passkey (WebAuthn PRF) ──────────────────────────────────────────────────

/** What `getClientExtensionResults()` returns for `prf`; not yet in the DOM lib. */
interface PrfResults {
  prf?: { enabled?: boolean; results?: { first?: ArrayBuffer } };
}

/** Is a passkey that can hold a key usable here? Never throws. */
export async function passkeySupported(): Promise<boolean> {
  try {
    return typeof window !== "undefined"
      && typeof window.PublicKeyCredential !== "undefined"
      && typeof window.PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable === "function"
      && await window.PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable();
  } catch {
    return false;
  }
}

/** The 32 bytes this authenticator derives for ``salt`` — the key material, which never leaves it. */
async function prfOutput(credentialId: Uint8Array | null, salt: Uint8Array): Promise<ArrayBuffer> {
  const assertion = await navigator.credentials.get({
    publicKey: {
      challenge: crypto.getRandomValues(new Uint8Array(32)),
      allowCredentials: credentialId ? [{ id: credentialId as BufferSource, type: "public-key" }] : [],
      userVerification: "required",
      timeout: WEBAUTHN_TIMEOUT_MS,
      extensions: { prf: { eval: { first: salt as BufferSource } } },
    } as PublicKeyCredentialRequestOptions,
  }) as PublicKeyCredential | null;
  if (!assertion) throw new VaultError("No passkey was presented.");
  const results = assertion.getClientExtensionResults() as PrfResults;
  const first = results.prf?.results?.first;
  if (!first) {
    throw new VaultError("This passkey cannot hold a key (the browser or authenticator does not "
      + "support the WebAuthn PRF extension). Use a passphrase instead.");
  }
  return first;
}

async function keyFromPrf(output: ArrayBuffer, context: string): Promise<CryptoKey> {
  // HKDF over the authenticator's output, bound to the patient this token is for.
  const material = await crypto.subtle.importKey("raw", output, "HKDF", false, ["deriveKey"]);
  return crypto.subtle.deriveKey(
    { name: "HKDF", hash: "SHA-256", salt: new Uint8Array(0),
      info: new TextEncoder().encode(`quantumcare-consent-token:${context}`) },
    material, { name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]);
}

/**
 * Register a passkey for this doctor and seal ``token`` under a key only that
 * authenticator can reproduce. The browser asks for a touch, twice: once to
 * create the credential, once to derive the key from it.
 */
export async function sealTokenWithPasskey(token: string, context: string,
                                           userName: string): Promise<PasskeySealed> {
  const credential = await navigator.credentials.create({
    publicKey: {
      challenge: crypto.getRandomValues(new Uint8Array(32)),
      rp: { name: RP_NAME },
      user: { id: crypto.getRandomValues(new Uint8Array(16)),
              name: userName, displayName: userName },
      pubKeyCredParams: [{ alg: -7, type: "public-key" }, { alg: -257, type: "public-key" }],
      authenticatorSelection: { residentKey: "required", userVerification: "required" },
      timeout: WEBAUTHN_TIMEOUT_MS,
      extensions: { prf: {} },
    } as PublicKeyCredentialCreationOptions,
  }) as PublicKeyCredential | null;
  if (!credential) throw new VaultError("No passkey was created.");
  // Say so now, not after a second prompt: the browser reports a platform
  // authenticator as available without promising it can hold a key.
  if ((credential.getClientExtensionResults() as PrfResults).prf?.enabled === false) {
    throw new VaultError("This device's passkey cannot hold a key (no WebAuthn PRF support). "
      + "Choose a passphrase instead.");
  }

  const credentialId = new Uint8Array(credential.rawId);
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const key = await keyFromPrf(await prfOutput(credentialId, salt), context);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  return { v: VAULT_VERSION, kdf: "WebAuthn-PRF", credentialId: b64url(credentialId),
           salt: b64(salt), iv: b64(iv), ct: b64(await encrypt(key, token, context, iv)) };
}

/** Unlock with the authenticator that sealed it. Asks for one touch. */
export async function openTokenWithPasskey(sealed: SealedToken, context: string): Promise<string> {
  if (!isPasskeySealed(sealed)) throw new VaultError("This token is protected by a passphrase, not a passkey.");
  const output = await prfOutput(unb64url(sealed.credentialId), unb64(sealed.salt));
  try {
    return await decrypt(await keyFromPrf(output, context), sealed, context);
  } catch {
    throw new VaultError("That passkey does not unlock this token, or the stored token was altered.");
  }
}

// ─── Shapes ──────────────────────────────────────────────────────────────────

function hasCommon(s: Partial<SealedCommon> | null): boolean {
  return Boolean(s && s.v === VAULT_VERSION
    && typeof s.salt === "string" && typeof s.iv === "string" && typeof s.ct === "string");
}

export function isPassphraseSealed(value: unknown): value is PassphraseSealed {
  const s = value as PassphraseSealed | null;
  return hasCommon(s) && s!.kdf === "PBKDF2-SHA256"
    && Number.isInteger(s!.iterations) && s!.iterations >= 100_000;
}

export function isPasskeySealed(value: unknown): value is PasskeySealed {
  const s = value as PasskeySealed | null;
  return hasCommon(s) && s!.kdf === "WebAuthn-PRF" && typeof s!.credentialId === "string"
    && s!.credentialId.length > 0;
}

export function isSealed(value: unknown): value is SealedToken {
  return isPassphraseSealed(value) || isPasskeySealed(value);
}

/** How a stored token is protected, for the screen to say so plainly. */
export function protectedBy(sealed: SealedToken): "passkey" | "passphrase" {
  return isPasskeySealed(sealed) ? "passkey" : "passphrase";
}
