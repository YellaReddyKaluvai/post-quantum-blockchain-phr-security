"use client";

import React, { useEffect, useRef, useState } from "react";
import { ShieldAlert, Loader2, Lock } from "lucide-react";
import { STEP_UP_EVENT, StepUpPrompt, stepUpVerify } from "@/lib/session";

/**
 * Password re-verification requested by the backend's risk policy.
 *
 * When recent activity scores MEDIUM/HIGH under a "verify" policy, a record
 * read answers 428 STEP_UP_REQUIRED. fetchWithAuth raises this dialog, and the
 * original request is retried once the password is confirmed. The reason the
 * system gives is shown, so the user is told *why* rather than just blocked.
 */
export default function StepUpDialog() {
  const [prompt, setPrompt] = useState<StepUpPrompt | null>(null);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const w = window as unknown as { __quantumcareStepUpReady?: boolean };
    w.__quantumcareStepUpReady = true;
    const onPrompt = (e: Event) => {
      setPrompt((e as CustomEvent<StepUpPrompt>).detail);
      setPassword("");
      setError("");
    };
    window.addEventListener(STEP_UP_EVENT, onPrompt);
    return () => {
      w.__quantumcareStepUpReady = false;
      window.removeEventListener(STEP_UP_EVENT, onPrompt);
    };
  }, []);

  useEffect(() => {
    if (prompt) inputRef.current?.focus();
  }, [prompt]);

  if (!prompt) return null;

  const close = (verified: boolean) => {
    prompt.resolve(verified);
    setPrompt(null);
    setPassword("");
    setError("");
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!password || busy) return;
    setBusy(true);
    setError("");
    try {
      await stepUpVerify(password);
      close(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Verification failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-900/50 backdrop-blur-sm p-4"
         role="dialog" aria-modal="true" aria-labelledby="step-up-title">
      <form onSubmit={submit} className="w-full max-w-md bg-white rounded-2xl shadow-xl border border-slate-100 p-6">
        <div className="flex items-center gap-2 mb-2">
          <ShieldAlert className="w-5 h-5 text-amber-500" />
          <h2 id="step-up-title" className="text-lg font-bold text-slate-800">Confirm it&apos;s you</h2>
          {prompt.risk_level && (
            <span className="ml-auto text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-100 text-amber-800">
              {prompt.risk_level} RISK
            </span>
          )}
        </div>
        <p className="text-sm text-slate-600 mb-3">{prompt.message}</p>
        {prompt.explanation && (
          <div className="mb-4 p-3 rounded-xl bg-slate-50 border border-slate-100">
            <p className="text-[10px] uppercase font-bold text-slate-400 tracking-wide mb-1">Why you are being asked</p>
            <p className="text-xs text-slate-600">{prompt.explanation}</p>
          </div>
        )}
        <label htmlFor="step-up-password" className="block text-xs font-bold text-slate-500 mb-1">Password</label>
        <div className="relative">
          <Lock className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            id="step-up-password"
            ref={inputRef}
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full pl-9 pr-3 py-2 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-200"
          />
        </div>
        {error && <p className="mt-2 text-sm font-semibold text-rose-600">{error}</p>}
        <div className="flex justify-end gap-2 mt-5">
          <button type="button" onClick={() => close(false)} disabled={busy}
                  className="px-4 py-2 rounded-xl text-sm font-bold text-slate-600 hover:bg-slate-50 disabled:opacity-50">
            Cancel
          </button>
          <button type="submit" disabled={!password || busy}
                  className="px-4 py-2 rounded-xl text-sm font-bold bg-cyan-600 text-white hover:bg-cyan-700 disabled:opacity-50 flex items-center gap-2">
            {busy && <Loader2 className="w-4 h-4 animate-spin" />}
            Verify and continue
          </button>
        </div>
      </form>
    </div>
  );
}
