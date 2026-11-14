"use client";
import { useEffect, useState } from "react";
import { workflowRequest } from "@/lib/session";
type Case = {
  id: string;
  user_id: string;
  requested_by: string;
  approved_by: string | null;
  evidence_reference: string;
  expires_at: string;
  consumed_at: string | null;
};
export default function Recovery() {
  const [cases, setCases] = useState<Case[]>([]),
    [user, setUser] = useState(""),
    [evidence, setEvidence] = useState(""),
    [password, setPassword] = useState(""),
    [otp, setOtp] = useState(""),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false);
  const refresh = () =>
    workflowRequest("auth/admin/mfa-recovery").then(setCases);
  useEffect(() => {
    refresh().catch((e) => setMessage(e.message));
  }, []);
  const run = async (path: string, extra: object = {}) => {
    setBusy(true);
    try {
      const r = await workflowRequest(`auth/admin/mfa-recovery${path}`, {
        password,
        otp,
        ...extra,
      });
      setMessage(r.message);
      setPassword("");
      setOtp("");
      await refresh();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Request failed");
    } finally {
      setBusy(false);
    }
  };
  return (
    <main className="p-6 space-y-5">
      <h1 className="text-2xl font-bold">Account identity recovery</h1>
      <p>
        Verify identity through your institution’s independent process first.
        Enter the case reference, not identity-document contents. Two different
        MFA-enabled administrators must approve. The account owner cannot
        approve their own recovery.
      </p>
      <p role="status">{message}</p>
      <label className="block">
        Your current password
        <input
          className="block border p-2"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </label>
      <label className="block">
        Your authenticator or recovery code
        <input
          className="block border p-2"
          value={otp}
          onChange={(e) => setOtp(e.target.value)}
        />
      </label>
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          void run("", { user_id: user, evidence_reference: evidence });
        }}
      >
        <label className="block">
          Account UUID
          <input
            required
            className="block border p-2 w-full"
            value={user}
            onChange={(e) => setUser(e.target.value)}
          />
        </label>
        <label className="block">
          Verified identity case reference
          <input
            required
            minLength={10}
            maxLength={300}
            className="block border p-2 w-full"
            value={evidence}
            onChange={(e) => setEvidence(e.target.value)}
          />
        </label>
        <button
          disabled={busy || !password || !otp}
          className="bg-cyan-700 text-white p-2 rounded"
        >
          Request recovery
        </button>
      </form>
      {cases.map((c) => (
        <article key={c.id} className="border rounded p-4">
          <p>Account: {c.user_id}</p>
          <p>Case: {c.evidence_reference}</p>
          <p>Requested by: {c.requested_by}</p>
          <p>Expires: {c.expires_at}</p>
          {c.consumed_at ? (
            <p>Completed</p>
          ) : c.approved_by ? (
            <p>Approved; awaiting account owner</p>
          ) : (
            <button
              disabled={busy || !password || !otp}
              onClick={() => {
                if (
                  window.confirm(
                    "Have you independently verified this person’s identity?",
                  )
                )
                  void run(`/${c.id}/approve`);
              }}
              className="underline"
            >
              Approve and email recovery link
            </button>
          )}
        </article>
      ))}
    </main>
  );
}
