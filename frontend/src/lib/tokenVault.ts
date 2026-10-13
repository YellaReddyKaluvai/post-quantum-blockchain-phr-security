// Passphrase protection for a consent token kept in the browser (spec §17).
//
// The consent token is the doctor's private ZKP witness: whoever holds it can
// prove the patient's consent. Kept in localStorage as plain text, any script
// on this origin — or anyone with the disk or a stray backup file — could take
// it. Sealed here, what is stored is AES-256-GCM ciphertext under a key derived
// from a passphrase only the doctor knows (PBKDF2-SHA-256), so a copy of the
// storage or a backup is useless without it.
//
// What it does not do: a script running at the moment the passphrase is typed
// could still capture it. It protects the token at rest, not a compromised page
// in use. WebCrypto only — no dependency, and the key never leaves SubtleCrypto.

export const VAULT_VERSION = 1;
export const KDF_ITERATIONS = 310_000;     // OWASP's PBKDF2-HMAC-SHA256 recommendation
export const MIN_PASSPHRASE_LENGTH = 8;

export interface SealedToken {
  v: number;
  kdf: "PBKDF2-SHA256";
  iterations: number;
  salt: string;   // base64, 16 bytes
  iv: string;     // base64, 12 bytes
  ct: string;     // base64, AES-256-GCM ciphertext + tag
}

export class VaultError extends Error {}

const b64 = (bytes: Uint8Array) => btoa(String.fromCharCode(...bytes));
const unb64 = (text: string) => Uint8Array.from(atob(text), (c) => c.charCodeAt(0));

async function deriveKey(passphrase: string, salt: Uint8Array, iterations: number): Promise<CryptoKey> {
  const material = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(passphrase), "PBKDF2", false, ["deriveKey"]);
  return crypto.subtle.deriveKey(
    { name: "PBKDF2", hash: "SHA-256", salt: salt as BufferSource, iterations },
    material, { name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]);
}

/** Encrypt ``token`` under ``passphrase``. The context (e.g. patient ID) is bound as associated data. */
export async function sealToken(token: string, passphrase: string, context: string): Promise<SealedToken> {
  if (passphrase.length < MIN_PASSPHRASE_LENGTH) {
    throw new VaultError(`Use a passphrase of at least ${MIN_PASSPHRASE_LENGTH} characters.`);
  }
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const key = await deriveKey(passphrase, salt, KDF_ITERATIONS);
  const ct = new Uint8Array(await crypto.subtle.encrypt(
    { name: "AES-GCM", iv: iv as BufferSource, additionalData: new TextEncoder().encode(context) },
    key, new TextEncoder().encode(token)));
  return { v: VAULT_VERSION, kdf: "PBKDF2-SHA256", iterations: KDF_ITERATIONS,
           salt: b64(salt), iv: b64(iv), ct: b64(ct) };
}

/** Decrypt; a wrong passphrase, a different context or any tampering fails the same way. */
export async function openToken(sealed: SealedToken, passphrase: string, context: string): Promise<string> {
  if (!isSealed(sealed)) throw new VaultError("Not a sealed consent token.");
  try {
    const key = await deriveKey(passphrase, unb64(sealed.salt), sealed.iterations);
    const plain = await crypto.subtle.decrypt(
      { name: "AES-GCM", iv: unb64(sealed.iv) as BufferSource,
        additionalData: new TextEncoder().encode(context) },
      key, unb64(sealed.ct) as BufferSource);
    return new TextDecoder().decode(plain);
  } catch {
    throw new VaultError("Wrong passphrase, or the stored token was altered.");
  }
}

export function isSealed(value: unknown): value is SealedToken {
  const s = value as SealedToken | null;
  return Boolean(s && s.v === VAULT_VERSION && s.kdf === "PBKDF2-SHA256"
    && typeof s.salt === "string" && typeof s.iv === "string" && typeof s.ct === "string"
    && Number.isInteger(s.iterations) && s.iterations >= 100_000);
}
