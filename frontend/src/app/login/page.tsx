"use client";

import React, { useState, Suspense } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ShieldCheck, User, Lock, ArrowRight, Loader2, Clock } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { login, setAuthCookies } from "../../lib/session";
import { normalizeRole, dashboardRouteMap } from "../../lib/iam";
import { useAuth } from "../../context/AuthContext";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { setSession } = useAuth();
  const [userId, setUserId] = useState("");
  const [password, setPassword] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const sessionExpired = searchParams.get("reason") === "expired";
  const returnTo = searchParams.get("from");

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (userId && password) {
      setLoading(true);
      try {
        const result = await login(userId, password);
        setAuthCookies(result.access_token, result.role, userId);
        setSession({
          role: result.role,
          userId: userId,
          accessToken: result.access_token,
        });
        const appRole = normalizeRole(result.role);
        const dashPath = appRole ? dashboardRouteMap[appRole] : "/login";
        // Return them to the page the expired session interrupted, but only if
        // their role is actually allowed there — a stale `from` must never
        // become a way around the role routing.
        const allowedPrefix = appRole ? dashboardRouteMap[appRole] : null;
        const canReturn =
          returnTo && allowedPrefix && returnTo.startsWith(allowedPrefix);
        router.push(canReturn ? returnTo : dashPath);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : "Network Error");
      } finally {
        setLoading(false);
      }
    }
  };

  const inputClass = "w-full bg-cyan-50/50 border border-cyan-100 shadow-[inset_0_2px_4px_rgba(8,145,178,0.05)] rounded-2xl py-3.5 pl-12 pr-4 text-slate-800 focus:bg-white focus:outline-none focus:border-cyan-400 focus:ring-[3px] focus:ring-cyan-100 transition-all text-sm font-bold placeholder-slate-500";
  const labelClass = "block text-[11px] font-extrabold text-teal-600/80 mb-2 uppercase tracking-widest";

  return (
    <div className="min-h-screen text-slate-700 flex flex-col pt-16 items-center p-4 relative overflow-hidden"
      style={{ background: "linear-gradient(135deg, #f9feff 0%, #f0fafd 20%, #f5fdf9 60%, #fdfffe 100%)" }}>

      {/* Decorative blobs */}
      <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] rounded-full bg-cyan-300/40 blur-[120px] pointer-events-none float-anim" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[50%] h-[50%] rounded-full bg-emerald-300/30 blur-[120px] pointer-events-none float-anim" style={{ animationDelay: "2s" }} />
      <div className="absolute top-[30%] right-[10%] w-[30%] h-[30%] rounded-full bg-sky-300/20 blur-[100px] pointer-events-none float-anim" style={{ animationDelay: "4s" }} />
      
      {/* Background Grid */}
      <div className="absolute inset-0 z-[-1] bg-[linear-gradient(to_right,#0891b20a_1px,transparent_1px),linear-gradient(to_bottom,#0891b20a_1px,transparent_1px)] bg-[size:32px_32px] [mask-image:radial-gradient(ellipse_70%_60%_at_50%_0%,#000_70%,transparent_100%)]" />

      <div className="w-full max-w-lg relative z-10">
        {/* Logo */}
        <Link href="/" className="flex items-center justify-center gap-3 mb-8 hover:opacity-80 transition-opacity">
          <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-cyan-400 to-teal-500 flex items-center justify-center shadow-lg shadow-cyan-200">
            <ShieldCheck className="w-6 h-6 text-white" />
          </div>
          <span className="text-2xl font-extrabold tracking-wider bg-clip-text text-transparent bg-gradient-to-r from-slate-800 to-slate-600 drop-shadow-sm">
            QuantumCare
          </span>
        </Link>

        {/* Card */}
        <motion.div
          initial={{ opacity: 0, y: 30, scale: 0.95 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.6, ease: "easeOut" }}
          className="card-3d gradient-border-card p-8 sm:p-10 rounded-[2rem] border border-white/60 shadow-[0_15px_60px_-15px_rgba(8,145,178,0.25)] relative overflow-hidden"
        >
          <div className="absolute inset-0 z-[-1] bg-gradient-to-b from-white to-cyan-50/30" />
          <div className="absolute -top-24 -right-24 w-48 h-48 bg-teal-400/10 rounded-full blur-3xl pointer-events-none" />
          <div className="absolute -bottom-24 -left-24 w-48 h-48 bg-cyan-400/10 rounded-full blur-3xl pointer-events-none" />
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-3/4 h-1 bg-gradient-to-r from-transparent via-cyan-400 to-transparent opacity-80 rounded-b-full" />

          <AnimatePresence mode="wait">
            <motion.div key="login" initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 20 }} transition={{ duration: 0.3 }}>
              <div className="mb-8 text-center">
                <h2 className="text-3xl font-black mb-2 inline-block text-cyan-900">
                  Welcome Back
                </h2>
                <p className="text-slate-500 text-sm mt-2 font-medium">Authenticate to access your secure portal.</p>
              </div>

              {sessionExpired && !error && (
                <div className="mb-5 p-3.5 rounded-xl bg-amber-50 border border-amber-100 text-amber-800 text-xs font-semibold flex items-start gap-2.5">
                  <Clock className="w-4 h-4 flex-shrink-0 mt-px" />
                  <span>
                    Your session timed out for security. Sign in again
                    {returnTo ? " to pick up where you left off." : "."}
                  </span>
                </div>
              )}
              {error && <div className="mb-5 p-3.5 rounded-xl bg-rose-50 border border-rose-100 text-rose-600 text-xs font-semibold">{error}</div>}

              <form onSubmit={handleLoginSubmit} className="space-y-5 mt-6">
                <div>
                  <label className={labelClass}>User ID</label>
                  <div className="relative group">
                    <User className="absolute left-4 top-1/2 -translate-y-1/2 w-[20px] h-[20px] text-teal-500 group-focus-within:text-cyan-500 group-focus-within:drop-shadow-sm transition-colors" />
                    <input type="text" required value={userId} onChange={e => setUserId(e.target.value)} className={inputClass} placeholder="PAT-2026-000001" />
                  </div>
                </div>
                <div>
                  <label className={labelClass}>Password</label>
                  <div className="relative group">
                    <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-[20px] h-[20px] text-teal-500 group-focus-within:text-cyan-500 group-focus-within:drop-shadow-sm transition-colors" />
                    <input type="password" required value={password} onChange={e => setPassword(e.target.value)} className={inputClass} placeholder="••••••••••••" />
                  </div>
                </div>

                <button type="submit" disabled={loading}
                  className="w-full mt-6 bg-gradient-to-r from-cyan-500 to-teal-500 hover:from-cyan-400 hover:to-teal-400 disabled:opacity-50 text-white py-4 rounded-2xl font-extrabold transition-all flex items-center justify-center gap-2 shadow-[0_8px_16px_-4px_rgba(8,145,178,0.4)] hover:shadow-[0_12px_20px_-4px_rgba(8,145,178,0.5)] hover:-translate-y-1">
                  {loading ? <Loader2 className="w-5 h-5 animate-spin"/> : "Authenticate Portal"} <ArrowRight className="w-5 h-5" />
                </button>
              </form>

              <div className="mt-8 text-center text-sm text-slate-500 font-medium">
                Don&apos;t have an Identity? <Link href="/signup" className="text-cyan-600 hover:text-cyan-500 font-extrabold ml-1 underline decoration-cyan-300 underline-offset-4 pointer-events-auto">Register strictly</Link>
              </div>
            </motion.div>
          </AnimatePresence>
        </motion.div>
        
        <p className="text-center text-[11px] font-bold text-teal-600/50 mt-10 tracking-widest uppercase">
          🔒 End-to-End Post-Quantum Lattice Node
        </p>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}
