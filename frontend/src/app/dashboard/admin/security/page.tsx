"use client";

import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Shield, ShieldAlert, Users, KeyRound, Activity, AlertTriangle, Loader2, Link2, Cloud } from "lucide-react";
import { getSecurityStats, getBlockchainStatus, getStorageStatus } from "@/lib/session";

interface SecurityStats {
  failed_login_attempts_24h: number;
  disabled_accounts: number;
  active_sessions: number;
  total_pqc_keypairs: number;
  active_crypto_identities: number;
}

interface BlockchainStatus {
  enabled: boolean;
  connected: boolean;
  network?: string | null;
  chain_id?: number;
  contract_address?: string | null;
  latest_block?: number;
  onchain_audit_entries?: number;
  anchors: { total: number; on_chain: number; simulated: number };
}

interface StorageStatus {
  configured: boolean;
  connected: boolean;
  bucket?: string | null;
  region?: string | null;
  error?: string | null;
  reports_total: number;
  reports_with_cloud_copy: number;
  reports_without_cloud_copy: number;
}

export default function SecurityPage() {
  const [stats, setStats] = useState<SecurityStats | null>(null);
  const [chain, setChain] = useState<BlockchainStatus | null>(null);
  const [storage, setStorage] = useState<StorageStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const fetchAll = async () => {
      try {
        setStats(await getSecurityStats());
      } catch {
        setError("Failed to load security statistics");
      }
      // Infrastructure health is fetched independently: a chain or bucket
      // being unreachable is exactly what this panel exists to report, so it
      // must not prevent the rest of the page rendering.
      try { setChain(await getBlockchainStatus()); } catch { setChain(null); }
      try { setStorage(await getStorageStatus()); } catch { setStorage(null); }
      setLoading(false);
    };
    fetchAll();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Loader2 className="w-10 h-10 text-cyan-500 animate-spin" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] text-slate-500">
        <ShieldAlert className="w-12 h-12 text-rose-400 mb-4" />
        <p className="font-bold text-lg text-slate-700 mb-2">Error Loading Data</p>
        <p>{error}</p>
      </div>
    );
  }

  const cards = [
    {
      title: "Failed Login Attempts (24h)",
      value: stats?.failed_login_attempts_24h || 0,
      icon: ShieldAlert,
      color: "text-rose-600",
      bg: "bg-rose-50",
      border: "border-rose-100",
      delay: 0.1
    },
    {
      title: "Disabled Accounts",
      value: stats?.disabled_accounts || 0,
      icon: Users,
      color: "text-slate-600",
      bg: "bg-slate-100",
      border: "border-slate-200",
      delay: 0.2
    },
    {
      title: "Active Sessions",
      value: stats?.active_sessions || 0,
      icon: Activity,
      color: "text-emerald-600",
      bg: "bg-emerald-50",
      border: "border-emerald-100",
      delay: 0.3
    },
    {
      title: "Total PQC Key Pairs",
      value: stats?.total_pqc_keypairs || 0,
      icon: KeyRound,
      color: "text-cyan-600",
      bg: "bg-cyan-50",
      border: "border-cyan-100",
      delay: 0.4
    },
    {
      title: "Active Cryptographic Identities",
      value: stats?.active_crypto_identities || 0,
      icon: Shield,
      color: "text-teal-600",
      bg: "bg-teal-50",
      border: "border-teal-100",
      delay: 0.5
    }
  ];

  return (
    <>
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="mb-8">
        <div className="flex items-center gap-3 mb-1">
          <Shield className="w-7 h-7 text-cyan-500" />
          <h2 className="text-2xl sm:text-3xl font-extrabold text-slate-800">Security Overview</h2>
        </div>
        <p className="text-sm text-slate-500">Monitor cryptographic infrastructure and authentication health.</p>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-8 p-4 bg-amber-50 border border-amber-100 rounded-2xl flex items-start gap-4"
      >
        <AlertTriangle className="w-6 h-6 text-amber-500 flex-shrink-0 mt-0.5" />
        <div>
          <h4 className="text-sm font-bold text-amber-800">Metadata Only Display</h4>
          <p className="text-sm text-amber-700/80 mt-1">
            This dashboard displays security metadata and usage statistics only. Cryptographic keys, encrypted payloads, and private patient data are never exposed or transmitted to the administration interface.
          </p>
        </div>
      </motion.div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {cards.map((c) => (
          <motion.div
            key={c.title}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: c.delay }}
            className={`p-6 rounded-3xl border ${c.border} bg-white shadow-sm hover:shadow-md transition-shadow relative overflow-hidden group`}
          >
            <div className={`absolute -right-6 -top-6 w-24 h-24 rounded-full ${c.bg} opacity-50 group-hover:scale-150 transition-transform duration-500`} />
            
            <div className={`w-12 h-12 rounded-2xl ${c.bg} flex items-center justify-center mb-6 relative z-10`}>
              <c.icon className={`w-6 h-6 ${c.color}`} />
            </div>
            
            <div className="relative z-10">
              <div className="text-4xl font-black text-slate-800 mb-2">{c.value.toLocaleString()}</div>
              <div className="text-sm font-bold text-slate-500 uppercase tracking-wide">{c.title}</div>
            </div>
          </motion.div>
        ))}
      </div>

      {/* Infrastructure health. Reports what is actually reachable rather than
          assuming it works — a simulated anchor or a missing cloud copy is
          precisely what an administrator needs to see. */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.5 }}
          className="p-6 rounded-3xl border border-slate-100 bg-white shadow-sm"
        >
          <div className="flex items-center gap-3 mb-4 pb-4 border-b border-slate-100">
            <Link2 className="w-5 h-5 text-violet-500" />
            <h3 className="text-lg font-bold text-slate-800">Blockchain Anchoring</h3>
            <span className={`ml-auto text-[10px] font-bold px-2.5 py-1 rounded-full ${
              chain?.connected ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"
            }`}>
              {chain?.connected ? "CONNECTED" : "UNREACHABLE"}
            </span>
          </div>

          {!chain ? (
            <p className="text-sm text-slate-500">Status unavailable.</p>
          ) : (
            <div className="space-y-2.5 text-sm">
              <p className="flex justify-between"><span className="text-slate-500">Network</span>
                <span className="font-semibold text-slate-800">{chain.network || "—"}</span></p>
              <p className="flex justify-between"><span className="text-slate-500">Chain ID</span>
                <span className="font-semibold text-slate-800 tabular-nums">{chain.chain_id ?? "—"}</span></p>
              {chain.connected && (
                <>
                  <p className="flex justify-between"><span className="text-slate-500">Latest block</span>
                    <span className="font-semibold text-slate-800 tabular-nums">{chain.latest_block ?? "—"}</span></p>
                  <p className="flex justify-between"><span className="text-slate-500">On-chain audit entries</span>
                    <span className="font-semibold text-slate-800 tabular-nums">{chain.onchain_audit_entries ?? "—"}</span></p>
                </>
              )}
              <div className="pt-3 mt-1 border-t border-slate-100 space-y-2">
                <p className="flex justify-between"><span className="text-slate-500">Anchors written on-chain</span>
                  <span className="font-bold text-emerald-600 tabular-nums">{chain.anchors.on_chain}</span></p>
                <p className="flex justify-between"><span className="text-slate-500">Locally simulated</span>
                  <span className={`font-bold tabular-nums ${chain.anchors.simulated > 0 ? "text-amber-600" : "text-slate-800"}`}>
                    {chain.anchors.simulated}
                  </span></p>
              </div>
              {chain.anchors.simulated > 0 && (
                <p className="text-xs text-amber-700 bg-amber-50 border border-amber-100 rounded-xl p-2.5 mt-2">
                  Simulated anchors were recorded while no chain was reachable. They are
                  tamper-evident locally but carry no on-chain proof.
                </p>
              )}
              {chain.contract_address && (
                <p className="text-[11px] font-mono text-slate-400 break-all pt-2">{chain.contract_address}</p>
              )}
            </div>
          )}
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.55 }}
          className="p-6 rounded-3xl border border-slate-100 bg-white shadow-sm"
        >
          <div className="flex items-center gap-3 mb-4 pb-4 border-b border-slate-100">
            <Cloud className="w-5 h-5 text-blue-500" />
            <h3 className="text-lg font-bold text-slate-800">Cloud Storage</h3>
            <span className={`ml-auto text-[10px] font-bold px-2.5 py-1 rounded-full ${
              storage?.connected ? "bg-emerald-50 text-emerald-700"
                : storage?.configured ? "bg-rose-50 text-rose-700" : "bg-slate-100 text-slate-600"
            }`}>
              {storage?.connected ? "CONNECTED" : storage?.configured ? "ERROR" : "NOT CONFIGURED"}
            </span>
          </div>

          {!storage ? (
            <p className="text-sm text-slate-500">Status unavailable.</p>
          ) : (
            <div className="space-y-2.5 text-sm">
              <p className="flex justify-between"><span className="text-slate-500">Bucket</span>
                <span className="font-semibold text-slate-800 truncate ml-3">{storage.bucket || "—"}</span></p>
              <p className="flex justify-between"><span className="text-slate-500">Region</span>
                <span className="font-semibold text-slate-800">{storage.region || "—"}</span></p>
              <div className="pt-3 mt-1 border-t border-slate-100 space-y-2">
                <p className="flex justify-between"><span className="text-slate-500">Reports with a cloud copy</span>
                  <span className="font-bold text-emerald-600 tabular-nums">
                    {storage.reports_with_cloud_copy}/{storage.reports_total}
                  </span></p>
                <p className="flex justify-between"><span className="text-slate-500">Without a cloud copy</span>
                  <span className={`font-bold tabular-nums ${storage.reports_without_cloud_copy > 0 ? "text-amber-600" : "text-slate-800"}`}>
                    {storage.reports_without_cloud_copy}
                  </span></p>
              </div>
              {storage.error && (
                <p className="text-xs text-rose-700 bg-rose-50 border border-rose-100 rounded-xl p-2.5 mt-2">
                  {storage.error}
                </p>
              )}
              {storage.reports_without_cloud_copy > 0 && !storage.error && (
                <p className="text-xs text-amber-700 bg-amber-50 border border-amber-100 rounded-xl p-2.5 mt-2">
                  These reports are still readable from the database, but have no
                  off-database copy. Run <span className="font-mono">backfill_s3_copies.py</span> to reconcile.
                </p>
              )}
            </div>
          )}
        </motion.div>
      </div>
    </>
  );
}
