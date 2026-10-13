"use client";

import React, { useCallback, useEffect, useState } from "react";
import { Fingerprint, Loader2, CheckCircle, XCircle, Download, KeyRound, Trash2, Lock, ShieldAlert } from "lucide-react";
import { USER_ID_COOKIE, collectConsentToken, requestZkpChallenge, submitZkpProof } from "@/lib/session";
import { PREFIX, ZKPError, commitmentFor, prove, verify } from "@/lib/zkpLattice";
import { MIN_PASSPHRASE_LENGTH, SealedToken, VaultError, isSealed, openToken, sealToken } from "@/lib/tokenVault";

// What this browser keeps: the public commitment, and the token sealed under the
// doctor's passphrase. ``token`` is only ever present in records written before
// sealing existed; the panel asks to protect those.
interface StoredToken {
  commitment: string;
  sealed?: SealedToken;
  token?: string;
}

interface ProofResult {
  verified: boolean;
  ms: number;
  bytes: number;
  postQuantum: boolean;
}

function doctorId(): string {
  const match = document.cookie.match(new RegExp(`(?:^|; )${USER_ID_COOKIE}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : "unknown";
}

const storageKey = (patientId: string) => `quantumcare.zkp.${doctorId()}.${patientId}`;

function readStored(patientId: string): StoredToken | null {
  try {
    const raw = localStorage.getItem(storageKey(patientId));
    return raw ? (JSON.parse(raw) as StoredToken) : null;
  } catch {
    return null;
  }
}

function writeStored(patientId: string, value: StoredToken | null): boolean {
  try {
    if (value) localStorage.setItem(storageKey(patientId), JSON.stringify(value));
    else localStorage.removeItem(storageKey(patientId));
    return true;
  } catch {
    return false;
  }
}

/**
 * Prove the patient's consent without sending the consent token (spec §17).
 *
 * The token is collected once, kept only in this browser — encrypted under the
 * doctor's passphrase (lib/tokenVault.ts) — and used here to
 * answer a fresh server challenge with a post-quantum lattice proof made by
 * src/lib/zkpLattice.ts. The server checks the proof against the public
 * commitment it kept; the token itself never crosses the network again.
 */
export default function ConsentProofPanel({ patientId }: { patientId: string }) {
  const [stored, setStored] = useState<StoredToken | null>(null);
  // The opened token, in memory only for as long as this page is open.
  const [unlocked, setUnlocked] = useState<string | null>(null);
  const [passphrase, setPassphrase] = useState("");
  const [confirmPassphrase, setConfirmPassphrase] = useState("");
  const [busy, setBusy] = useState<"" | "collect" | "prove" | "seal">("");
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [result, setResult] = useState<ProofResult | null>(null);
  const [pasting, setPasting] = useState(false);
  const [pasted, setPasted] = useState("");

  useEffect(() => { setStored(readStored(patientId)); setUnlocked(null); }, [patientId]);

  const newPassphraseProblem = (): string | null => {
    if (passphrase.length < MIN_PASSPHRASE_LENGTH) return `Choose a passphrase of at least ${MIN_PASSPHRASE_LENGTH} characters.`;
    if (passphrase !== confirmPassphrase) return "The two passphrases do not match.";
    return null;
  };

  /** Seal ``token`` under the passphrase entered and keep only the sealed form. */
  const keepSealed = useCallback(async (token: string, commitment: string) => {
    const sealed = await sealToken(token, passphrase, patientId);
    const value: StoredToken = { commitment, sealed };
    setStored(value);
    setUnlocked(token);
    setPassphrase("");
    setConfirmPassphrase("");
    if (!writeStored(patientId, value)) {
      setNote("This browser will not keep the token (storage is blocked). Download the encrypted backup now — it cannot be collected again.");
    }
  }, [passphrase, patientId]);

  const collect = async () => {
    if (busy) return;
    const problem = newPassphraseProblem();
    if (problem) { setError(problem); return; }
    setBusy("collect");
    setError("");
    setNote("");
    try {
      const t = await collectConsentToken(patientId);
      if (!t.consent_token.startsWith(PREFIX)) {
        setError("This consent uses the legacy, non-post-quantum token, which this page does not prove. Ask the patient to re-approve.");
        return;
      }
      await keepSealed(t.consent_token, t.commitment);
      setNote("Token collected and stored encrypted under your passphrase. The server has discarded its copy — download the encrypted backup if you use more than one device.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to collect the token");
    } finally {
      setBusy("");
    }
  };

  const usePasted = async () => {
    setError("");
    try {
      const raw = pasted.trim();
      const parsed = raw.startsWith("{")
        ? JSON.parse(raw) as { token?: string; sealed?: unknown; commitment?: string } : null;
      if (parsed && isSealed(parsed.sealed) && parsed.commitment) {
        // An encrypted backup: kept as it is; the passphrase opens it when proving.
        const value: StoredToken = { commitment: parsed.commitment, sealed: parsed.sealed };
        setStored(value);
        writeStored(patientId, value);
      } else {
        const token = parsed ? parsed.token ?? "" : raw;
        const commitment = commitmentFor(token);              // throws on a malformed token
        const problem = newPassphraseProblem();
        if (problem) { setError(problem); return; }
        setBusy("seal");
        await keepSealed(token, commitment);
      }
      setPasting(false);
      setPasted("");
    } catch (e) {
      setError(e instanceof ZKPError || e instanceof VaultError ? e.message : "That is not a consent token or a token backup.");
    } finally {
      setBusy("");
    }
  };

  /** A token stored before sealing existed: encrypt it in place. */
  const protectLegacy = async () => {
    if (!stored?.token || busy) return;
    const problem = newPassphraseProblem();
    if (problem) { setError(problem); return; }
    setBusy("seal");
    setError("");
    try {
      await keepSealed(stored.token, stored.commitment);
      setNote("The token is now stored encrypted under your passphrase.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not protect the token");
    } finally {
      setBusy("");
    }
  };

  const runProof = async () => {
    if (!stored || busy) return;
    setBusy("prove");
    setError("");
    setResult(null);
    try {
      let token = unlocked ?? stored.token ?? null;
      if (!token && stored.sealed) {
        token = await openToken(stored.sealed, passphrase, patientId);
        setUnlocked(token);
        setPassphrase("");
      }
      if (!token) throw new VaultError("Enter your passphrase to unlock the token.");
      const ch = await requestZkpChallenge(patientId);
      // Yield once so the "Proving…" state paints before the computation runs.
      await new Promise((r) => setTimeout(r, 0));
      const started = performance.now();
      const proof = prove(token, ch.challenge, ch.context);
      const ms = Math.round(performance.now() - started);
      if (!verify(stored.commitment, proof.proof, ch.challenge, ch.context)) {
        setError("The proof does not check against this token's commitment, so it was not sent. The stored token may belong to a different consent.");
        return;
      }
      const res = await submitZkpProof({ challenge: ch.challenge, scheme: proof.scheme, proof: proof.proof });
      setResult({ verified: Boolean(res.verified), ms, bytes: Math.round((proof.proof.length * 3) / 4),
        postQuantum: Boolean(res.post_quantum_secure) });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Proof failed");
    } finally {
      setBusy("");
    }
  };

  const download = () => {
    if (!stored?.sealed) return;
    // The encrypted form only: a lost backup file is useless without the passphrase.
    const backup = { patient_id: patientId, commitment: stored.commitment, sealed: stored.sealed };
    const blob = new Blob([JSON.stringify(backup, null, 1)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `consent-token-${patientId.slice(0, 8)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const forget = () => {
    if (!window.confirm("Remove the token from this browser? Without a backup it cannot be recovered; the patient would have to re-approve.")) return;
    writeStored(patientId, null);
    setStored(null);
    setUnlocked(null);
    setResult(null);
  };

  const input = "w-full px-3 py-2 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-200";
  const newPassphraseFields = (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
      <div>
        <label htmlFor="zkp-pass" className="block text-xs font-bold text-slate-500 mb-1">Passphrase to protect the token</label>
        <input id="zkp-pass" type="password" autoComplete="new-password" value={passphrase}
          onChange={(e) => setPassphrase(e.target.value)} className={input} />
      </div>
      <div>
        <label htmlFor="zkp-pass2" className="block text-xs font-bold text-slate-500 mb-1">Repeat passphrase</label>
        <input id="zkp-pass2" type="password" autoComplete="new-password" value={confirmPassphrase}
          onChange={(e) => setConfirmPassphrase(e.target.value)} className={input} />
      </div>
      <p className="sm:col-span-2 text-[11px] text-slate-400">
        At least {MIN_PASSPHRASE_LENGTH} characters. The token is stored only encrypted under it (AES-256-GCM,
        PBKDF2-SHA-256); it cannot be recovered without it.
      </p>
    </div>
  );

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-6">
      <div className="flex items-center gap-3 mb-3 border-b border-slate-100 pb-4">
        <Fingerprint className="w-5 h-5 text-indigo-600" />
        <div>
          <h2 className="text-lg font-bold text-slate-800">Consent Proof</h2>
          <p className="text-xs text-slate-500">
            Prove you hold this patient&apos;s consent token without sending it — a post-quantum
            zero-knowledge proof made in this browser.
          </p>
        </div>
      </div>

      {note && <p className="mb-3 text-xs font-semibold text-amber-700 bg-amber-50 border border-amber-100 rounded-lg p-2">{note}</p>}
      {error && <p className="mb-3 text-sm font-semibold text-rose-600" role="alert">{error}</p>}

      {!stored ? (
        <div className="space-y-3">
          <p className="text-sm text-slate-600">
            When the patient approved your request a one-time consent token was issued. Collect it once;
            it is kept in this browser, encrypted under your passphrase, and the server keeps only its
            public commitment.
          </p>
          {newPassphraseFields}
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={collect} disabled={busy !== ""}
              className="px-4 py-2 rounded-xl text-sm font-bold bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 flex items-center gap-2">
              {busy === "collect" ? <Loader2 className="w-4 h-4 animate-spin" /> : <KeyRound className="w-4 h-4" />}
              Collect consent token
            </button>
            <button type="button" onClick={() => setPasting((p) => !p)}
              className="px-4 py-2 rounded-xl text-sm font-bold text-slate-600 border border-slate-200 hover:bg-slate-50">
              Use a saved token
            </button>
          </div>
          {pasting && (
            <div className="space-y-2">
              <label htmlFor="zkp-paste" className="block text-xs font-bold text-slate-500">Token or backup file contents (an encrypted backup needs no new passphrase)</label>
              <textarea id="zkp-paste" rows={3} value={pasted} onChange={(e) => setPasted(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-slate-200 text-xs font-mono" placeholder="mlwe1:…" />
              <button type="button" onClick={usePasted} disabled={!pasted.trim() || busy !== ""}
                className="px-3 py-1.5 rounded-lg text-xs font-bold bg-slate-800 text-white disabled:opacity-50">
                Use this token
              </button>
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-sm text-slate-600 flex items-center gap-1.5 flex-wrap">
            {stored.sealed && <Lock className="w-3.5 h-3.5 text-emerald-600" />}
            Token held in this browser{stored.sealed ? ", encrypted" : ""} · <span className="font-semibold">mlwe-v1</span> (Module-LWE / Module-SIS, ML-DSA-65 parameters)
            {unlocked && <span className="text-emerald-700 font-semibold">· unlocked for this page</span>}
          </p>
          {!stored.sealed && stored.token && (
            <div className="p-3 rounded-xl bg-amber-50 border border-amber-200 space-y-2">
              <p className="text-xs font-bold text-amber-900 flex items-center gap-1.5">
                <ShieldAlert className="w-4 h-4" /> Stored without protection
              </p>
              <p className="text-xs text-amber-900">
                This token was saved before tokens were encrypted, so any script on this site could read it.
                Set a passphrase to encrypt it in place.
              </p>
              {newPassphraseFields}
              <button type="button" onClick={protectLegacy} disabled={busy !== ""}
                className="px-3 py-1.5 rounded-lg text-xs font-bold bg-amber-600 text-white hover:bg-amber-700 disabled:opacity-50 flex items-center gap-1.5">
                {busy === "seal" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Lock className="w-3.5 h-3.5" />}
                Encrypt it now
              </button>
            </div>
          )}
          {stored.sealed && !unlocked && (
            <div>
              <label htmlFor="zkp-unlock" className="block text-xs font-bold text-slate-500 mb-1">Passphrase</label>
              <input id="zkp-unlock" type="password" autoComplete="current-password" value={passphrase}
                onChange={(e) => setPassphrase(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") runProof(); }}
                className={input} />
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={runProof}
              disabled={busy !== "" || (Boolean(stored.sealed) && !unlocked && !passphrase)}
              className="px-4 py-2 rounded-xl text-sm font-bold bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 flex items-center gap-2">
              {busy === "prove" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Fingerprint className="w-4 h-4" />}
              {busy === "prove" ? "Proving…" : "Prove consent"}
            </button>
            {stored.sealed && (
              <button type="button" onClick={download}
                className="px-3 py-2 rounded-xl text-xs font-bold text-slate-600 border border-slate-200 hover:bg-slate-50 flex items-center gap-1">
                <Download className="w-3.5 h-3.5" /> Encrypted backup
              </button>
            )}
            <button type="button" onClick={forget}
              className="px-3 py-2 rounded-xl text-xs font-bold text-rose-600 hover:bg-rose-50 flex items-center gap-1">
              <Trash2 className="w-3.5 h-3.5" /> Forget
            </button>
          </div>
          {result && (
            <div className={`p-3 rounded-xl border text-sm ${result.verified ? "bg-emerald-50 border-emerald-100 text-emerald-800" : "bg-rose-50 border-rose-100 text-rose-700"}`}>
              <p className="font-bold flex items-center gap-2">
                {result.verified ? <CheckCircle className="w-4 h-4" /> : <XCircle className="w-4 h-4" />}
                {result.verified ? "Consent proven" : "The server rejected the proof"}
              </p>
              <p className="text-xs mt-1">
                Proof made in {result.ms} ms ({(result.bytes / 1024).toFixed(1)} KB). The token never left this browser
                {result.postQuantum ? "; the proof rests on lattice problems, not discrete logarithms." : "."}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
