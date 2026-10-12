"use client";

import React, { useCallback, useEffect, useState } from "react";
import { Fingerprint, Loader2, CheckCircle, XCircle, Download, KeyRound, Trash2 } from "lucide-react";
import { USER_ID_COOKIE, collectConsentToken, requestZkpChallenge, submitZkpProof } from "@/lib/session";
import { PREFIX, ZKPError, commitmentFor, prove, verify } from "@/lib/zkpLattice";

interface StoredToken {
  token: string;
  commitment: string;
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
 * The token is collected once, kept only in this browser, and used here to
 * answer a fresh server challenge with a post-quantum lattice proof made by
 * src/lib/zkpLattice.ts. The server checks the proof against the public
 * commitment it kept; the token itself never crosses the network again.
 */
export default function ConsentProofPanel({ patientId }: { patientId: string }) {
  const [stored, setStored] = useState<StoredToken | null>(null);
  const [busy, setBusy] = useState<"" | "collect" | "prove">("");
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [result, setResult] = useState<ProofResult | null>(null);
  const [pasting, setPasting] = useState(false);
  const [pasted, setPasted] = useState("");

  useEffect(() => { setStored(readStored(patientId)); }, [patientId]);

  const keep = useCallback((value: StoredToken) => {
    setStored(value);
    if (!writeStored(patientId, value)) {
      setNote("This browser will not keep the token (storage is blocked). Download a backup now — it cannot be collected again.");
    }
  }, [patientId]);

  const collect = async () => {
    if (busy) return;
    setBusy("collect");
    setError("");
    setNote("");
    try {
      const t = await collectConsentToken(patientId);
      if (!t.consent_token.startsWith(PREFIX)) {
        setError("This consent uses the legacy, non-post-quantum token, which this page does not prove. Ask the patient to re-approve.");
        return;
      }
      keep({ token: t.consent_token, commitment: t.commitment });
      setNote("Token collected. The server has discarded its copy — download a backup if you use more than one device.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to collect the token");
    } finally {
      setBusy("");
    }
  };

  const usePasted = () => {
    setError("");
    try {
      const raw = pasted.trim();
      const token = raw.startsWith("{") ? (JSON.parse(raw) as { token?: string }).token ?? "" : raw;
      keep({ token, commitment: commitmentFor(token) });   // throws on a malformed token
      setPasting(false);
      setPasted("");
    } catch (e) {
      setError(e instanceof ZKPError ? e.message : "That is not a consent token or a token backup.");
    }
  };

  const runProof = async () => {
    if (!stored || busy) return;
    setBusy("prove");
    setError("");
    setResult(null);
    try {
      const ch = await requestZkpChallenge(patientId);
      // Yield once so the "Proving…" state paints before the computation runs.
      await new Promise((r) => setTimeout(r, 0));
      const started = performance.now();
      const proof = prove(stored.token, ch.challenge, ch.context);
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
    if (!stored) return;
    const blob = new Blob([JSON.stringify({ patient_id: patientId, ...stored }, null, 1)], { type: "application/json" });
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
    setResult(null);
  };

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
            it is kept in this browser and the server keeps only its public commitment.
          </p>
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
              <label htmlFor="zkp-paste" className="block text-xs font-bold text-slate-500">Token or backup file contents</label>
              <textarea id="zkp-paste" rows={3} value={pasted} onChange={(e) => setPasted(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-slate-200 text-xs font-mono" placeholder="mlwe1:…" />
              <button type="button" onClick={usePasted} disabled={!pasted.trim()}
                className="px-3 py-1.5 rounded-lg text-xs font-bold bg-slate-800 text-white disabled:opacity-50">
                Use this token
              </button>
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-sm text-slate-600">
            Token held in this browser · <span className="font-semibold">mlwe-v1</span> (Module-LWE / Module-SIS, ML-DSA-65 parameters)
          </p>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={runProof} disabled={busy !== ""}
              className="px-4 py-2 rounded-xl text-sm font-bold bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 flex items-center gap-2">
              {busy === "prove" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Fingerprint className="w-4 h-4" />}
              {busy === "prove" ? "Proving…" : "Prove consent"}
            </button>
            <button type="button" onClick={download}
              className="px-3 py-2 rounded-xl text-xs font-bold text-slate-600 border border-slate-200 hover:bg-slate-50 flex items-center gap-1">
              <Download className="w-3.5 h-3.5" /> Backup
            </button>
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
