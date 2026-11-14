"use client";
import React, { useEffect, useState } from "react";
import Link from "next/link";
import { accountRequest, clearAuthCookies } from "@/lib/session";

interface KeyVersion { version: number; current: boolean; revoked_at: string | null; created_at: string }
const input = "w-full border border-slate-300 rounded-xl p-3 mt-1";
const button = "px-4 py-2 rounded-xl bg-cyan-700 text-white disabled:opacity-50";

export default function AccountSecurity() {
  const [enabled, setEnabled] = useState(false);
  const [password, setPassword] = useState("");
  const [otp, setOtp] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [secret, setSecret] = useState("");
  const [code, setCode] = useState("");
  const [codes, setCodes] = useState<string[]>([]);
  const [keys, setKeys] = useState<KeyVersion[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const refresh = async () => {
    const [state, versions] = await Promise.all([accountRequest("security"), accountRequest("keys")]);
    setEnabled(state.mfa_enabled); setKeys(versions);
  };
  useEffect(() => { refresh().catch(e => setError(e instanceof Error ? e.message : "Unable to load security settings")); }, []);
  const act = async (path: string, extra: object = {}) => {
    if (busy) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const result = await accountRequest(path, {password, otp: otp || undefined, ...extra});
      setMessage(result.message || "Completed.");
      if (path === "mfa/disable") {setCodes([]); setSecret("");}
      if (result.secret) setSecret(result.secret);
      if (result.recovery_codes) { setCodes(result.recovery_codes); setSecret(""); }
      if (path === "password/change") {
        clearAuthCookies(); window.location.assign("/login"); return;
      }
      setPassword(""); setOtp(""); setCode(""); await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Account action failed"); }
    finally { setBusy(false); }
  };
  return <main className="max-w-3xl mx-auto w-full p-6 space-y-6">
    <Link href="/dashboard" className="text-cyan-700">← Dashboard</Link>
    <h1 className="text-3xl font-bold">Account security</h1>
    {message && <p role="status" className="p-3 rounded-xl bg-emerald-50 text-emerald-800">{message}</p>}
    {error && <p role="alert" className="p-3 rounded-xl bg-rose-50 text-rose-800">{error}</p>}
    <section className="bg-white border rounded-2xl p-6 space-y-4">
      <h2 className="text-xl font-semibold">Verify your identity</h2>
      <p>Enter your current password before changing security settings. If MFA is enabled, also enter a fresh authenticator code or an unused recovery code.</p>
      <label className="block">Current password<input type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} className={input} /></label>
      <label className="block">Authenticator / recovery code<input autoComplete="one-time-code" value={otp} onChange={e => setOtp(e.target.value)} className={input} /></label>
    </section>
    <form className="bg-white border rounded-2xl p-6 space-y-4" onSubmit={e => {e.preventDefault(); if (newPassword !== confirmPassword) {setError("Passwords do not match."); return;} void act("password/change", {new_password: newPassword});}}>
      <h2 className="text-xl font-semibold">Change password</h2>
      <label className="block">New password (at least 12 characters)<input required minLength={12} type="password" autoComplete="new-password" value={newPassword} onChange={e => setNewPassword(e.target.value)} className={input} /></label>
      <label className="block">Confirm new password<input required type="password" autoComplete="new-password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} className={input} /></label>
      <button disabled={busy || !password} className={button}>Change password and end all sessions</button>
    </form>
    <section className="bg-white border rounded-2xl p-6 space-y-4">
      <h2 className="text-xl font-semibold">Authenticator MFA: {enabled ? "enabled" : "not enabled"}</h2>
      {!enabled && !secret && <button disabled={busy || !password} onClick={() => act("mfa/setup")} className={button}>Set up authenticator</button>}
      {secret && <div className="space-y-4">
        <p>In your authenticator app, add a time-based account named QuantumCare and enter this setup key. Setup expires after 10 minutes.</p>
        <code className="block break-all bg-slate-100 p-3">{secret}</code>
        <label className="block">Six-digit code<input inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code} onChange={e => setCode(e.target.value)} className={input} /></label>
        <button disabled={busy || code.length !== 6} onClick={() => act("mfa/confirm", {code})} className={button}>Enable MFA</button>
      </div>}
      {enabled && <button disabled={busy || !password || !otp} onClick={() => {if (window.confirm("Disable MFA for this account?")) void act("mfa/disable");}} className={button}>Disable MFA</button>}
      {codes.length > 0 && <div><h3 className="font-bold">Save your recovery codes now</h3><p>Each code works once. They will not be displayed again. Keep them outside this browser.</p><pre className="bg-slate-100 p-4 mt-2">{codes.join("\n")}</pre><button onClick={() => setCodes([])} className="underline mt-2">I have saved these codes</button></div>}
    </section>
    <section className="bg-white border rounded-2xl p-6 space-y-4">
      <h2 className="text-xl font-semibold">Post-quantum keys</h2>
      <p>Rotation uses fresh keys for new records while preserving historical records. Revocation withholds records encrypted or signed using that version; use it only for suspected compromise.</p>
      <button disabled={busy || !password} onClick={() => act("keys/rotate")} className={button}>Rotate keys</button>
      <ul className="space-y-2">{keys.map(key => <li key={key.version} className="border rounded-xl p-3 flex justify-between gap-3"><span>Version {key.version} · {key.revoked_at ? "Revoked" : key.current ? "Current" : "Historical"}</span>{!key.current && !key.revoked_at && <button disabled={busy || !password} className="text-rose-700 underline" onClick={() => {if (window.confirm(`Revoke version ${key.version}? Affected records will no longer be released.`)) void act("keys/revoke", {version: key.version});}}>Revoke</button>}</li>)}</ul>
    </section>
  </main>;
}
