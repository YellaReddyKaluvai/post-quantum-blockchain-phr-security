"use client";
import React, { useEffect, useState } from "react";
import Link from "next/link";
import { recoveryRequest } from "@/lib/session";

export default function PasswordRecovery({reset = false}: {reset?: boolean}) {
  const [email, setEmail] = useState("");
  const [token, setToken] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [otp, setOtp] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (reset) {
      setToken(new URLSearchParams(window.location.hash.slice(1)).get("token") || "");
      window.history.replaceState(null, "", window.location.pathname);
    }
  }, [reset]);
  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); if (busy) return;
    setError(""); setMessage("");
    if (reset && password !== confirm) {setError("Passwords do not match."); return;}
    setBusy(true);
    try {
      const result = await recoveryRequest(reset ? "reset" : "forgot", reset ? {token, new_password: password, otp: otp || undefined} : {email});
      setMessage(result.message); if (reset) {setPassword(""); setConfirm(""); setToken(""); setOtp("");}
    } catch (e) {setError(e instanceof Error ? e.message : "Request failed");}
    finally {setBusy(false);}
  };
  const input = "w-full border rounded-xl p-3 mt-1";
  return <main className="max-w-lg w-full mx-auto p-6 mt-12 bg-white border rounded-2xl space-y-5">
    <h1 className="text-2xl font-bold">{reset ? "Choose a new password" : "Recover your account"}</h1>
    {message && <p role="status" className="text-emerald-800">{message}</p>}
    {error && <p role="alert" className="text-rose-700">{error}</p>}
    <form onSubmit={submit} className="space-y-4">
      {reset ? <>
        {!token && !message && <p>This reset link is missing or has already been used in this page. Request a new link.</p>}
        <label className="block">New password (12+ characters)<input required type="password" minLength={12} autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)} className={input} /></label>
        <label className="block">Confirm password<input required type="password" autoComplete="new-password" value={confirm} onChange={e => setConfirm(e.target.value)} className={input} /></label>
        <label className="block">Authenticator / recovery code (if MFA enabled)<input autoComplete="one-time-code" value={otp} onChange={e => setOtp(e.target.value)} className={input} /></label>
      </> : <label className="block">Account email<input required type="email" autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} className={input} /></label>}
      <button disabled={busy || (reset && !token)} className="px-4 py-3 bg-cyan-700 text-white rounded-xl disabled:opacity-50">{busy ? "Working…" : reset ? "Reset password" : "Send recovery link"}</button>
    </form>
    <Link href="/login" className="block text-cyan-700">Back to sign in</Link>
  </main>;
}
