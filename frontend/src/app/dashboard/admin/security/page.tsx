"use client";

import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Shield, ShieldAlert, Users, KeyRound, Activity, AlertTriangle, Loader2 } from "lucide-react";
import { getSecurityStats } from "@/lib/session";

interface SecurityStats {
  failed_login_attempts_24h: number;
  disabled_accounts: number;
  active_sessions: number;
  total_pqc_keypairs: number;
  active_crypto_identities: number;
}

export default function SecurityPage() {
  const [stats, setStats] = useState<SecurityStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const data = await getSecurityStats();
        setStats(data);
      } catch {
        setError("Failed to load security statistics");
      } finally {
        setLoading(false);
      }
    };
    fetchStats();
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
    </>
  );
}
