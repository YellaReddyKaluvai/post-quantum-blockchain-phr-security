"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
const base = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
export default function AccountLinkAction({
  recovery = false,
}: {
  recovery?: boolean;
}) {
  const [token, setToken] = useState(""),
    [email, setEmail] = useState(""),
    [password, setPassword] = useState(""),
    [confirm, setConfirm] = useState(""),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    const value =
      new URLSearchParams(location.hash.slice(1)).get("token") || "";
    queueMicrotask(() => setToken(value));
    if (value) history.replaceState(null, "", location.pathname);
  }, []);
  const run = async (path: string, body: object) => {
    setBusy(true);
    try {
      const r = await fetch(`${base}/api/auth/${path}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "QuantumCare",
        },
        body: JSON.stringify(body),
      });
      const data = await r.json();
      if (!r.ok)
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : "Unable to complete request",
        );
      setMessage(data.message);
      if (path !== "email/request") setToken("");
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Request failed");
    } finally {
      setBusy(false);
    }
  };
  return (
    <main className="max-w-lg mx-auto p-8 space-y-5">
      <h1 className="text-2xl font-bold">
        {recovery ? "Complete approved MFA recovery" : "Verify your email"}
      </h1>
      <p role="status">{message}</p>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (recovery) {
            if (password !== confirm) {
              setMessage("Passwords do not match");
              return;
            }
            void run("mfa/recover", { token, new_password: password });
          } else
            void run(
              token ? "email/verify" : "email/request",
              token ? { token } : { email },
            );
        }}
      >
        {recovery ? (
          <>
            <p>
              Use the link sent after two administrators verified your identity.
              All sessions will end. Enroll a new authenticator after signing
              in.
            </p>
            <label className="block">
              New password
              <input
                className="block border p-3 w-full"
                required
                minLength={12}
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            <label className="block">
              Confirm password
              <input
                className="block border p-3 w-full"
                required
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
              />
            </label>
          </>
        ) : (
          !token && (
            <label>
              Email
              <input
                required
                className="block border p-3 w-full"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </label>
          )
        )}
        <button
          disabled={busy || (recovery && !token)}
          className="px-4 py-2 bg-cyan-700 text-white rounded"
        >
          {recovery
            ? "Reset password and remove lost MFA"
            : token
              ? "Confirm email ownership"
              : "Send verification link"}
        </button>
      </form>
      <Link href="/login">Back to sign in</Link>
    </main>
  );
}
