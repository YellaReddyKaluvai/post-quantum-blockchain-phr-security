"use client";

import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { ShieldCheck, User, Clock, Activity, Key, Shield, Laptop } from "lucide-react";
import { getPatientSecurity } from "@/lib/session";

export default function SecurityCenterPage() {
  const [loading, setLoading] = useState(true);
  const [securityData, setSecurityData] = useState<any>(null);

  useEffect(() => {
    async function loadData() {
      try {
        const data = await getPatientSecurity();
        setSecurityData(data);
      } catch (error) {
        console.error("Failed to load security info:", error);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  if (loading) {
    return (
      <div className="space-y-6 max-w-5xl mx-auto">
        <div className="h-8 w-48 bg-slate-200 animate-pulse rounded-md"></div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="bg-white rounded-2xl h-64 animate-pulse shadow-sm border border-slate-100"></div>
          <div className="bg-white rounded-2xl h-64 animate-pulse shadow-sm border border-slate-100"></div>
        </div>
        <div className="bg-white rounded-2xl h-40 animate-pulse shadow-sm border border-slate-100 mt-6"></div>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-xl md:text-2xl font-bold text-slate-800">Security Center</h1>
        <p className="text-slate-500 mt-1">Review your account security and post-quantum protection status.</p>
      </motion.div>

      {/* PQC Protection Banner */}
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 0.1 }}
        className="bg-gradient-to-br from-slate-900 to-slate-800 rounded-3xl p-8 text-white shadow-xl relative overflow-hidden"
      >
        <div className="absolute top-0 right-0 w-64 h-64 bg-emerald-500/10 rounded-full blur-3xl"></div>
        <div className="absolute bottom-0 left-0 w-64 h-64 bg-cyan-500/10 rounded-full blur-3xl"></div>
        
        <div className="relative z-10 flex flex-col md:flex-row items-center gap-8">
          <div className="w-24 h-24 rounded-full bg-gradient-to-br from-emerald-400 to-cyan-500 p-1 flex-shrink-0 shadow-lg shadow-cyan-900/50">
            <div className="w-full h-full bg-slate-900 rounded-full flex items-center justify-center">
              <ShieldCheck className="w-12 h-12 text-transparent bg-clip-text bg-gradient-to-br from-emerald-400 to-cyan-400" />
            </div>
          </div>
          
          <div className="flex-1 text-center md:text-left">
            <div className="flex flex-col md:flex-row md:items-center gap-3 mb-2">
              <h2 className="text-2xl font-bold">Post-Quantum Protection</h2>
              <span className="inline-flex items-center justify-center px-3 py-1 rounded-full text-xs font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 w-fit mx-auto md:mx-0">
                <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 mr-2 animate-pulse"></div>
                Active & Enabled
              </span>
            </div>
            <p className="text-slate-300 leading-relaxed max-w-2xl">
              Your medical records and personal data are secured using military-grade Post-Quantum Cryptography (PQC). 
              Our blockchain infrastructure is completely immune to both classical and quantum computer attacks.
            </p>
          </div>
        </div>
      </motion.div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Account Information */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden"
        >
          <div className="p-6 border-b border-slate-100 flex items-center gap-3">
            <div className="p-2 bg-blue-50 text-blue-600 rounded-xl">
              <User className="w-5 h-5" />
            </div>
            <h2 className="text-lg font-bold text-slate-800">Account Identity</h2>
          </div>
          <div className="p-6 space-y-4">
            <div className="flex justify-between items-center p-3 bg-slate-50 rounded-xl border border-slate-100">
              <div className="flex items-center gap-3">
                <Key className="w-5 h-5 text-slate-400" />
                <span className="text-sm font-semibold text-slate-700">User ID</span>
              </div>
              <span className="text-sm font-mono font-bold text-slate-800">{securityData?.account_info?.user_id || "N/A"}</span>
            </div>
            
            <div className="flex justify-between items-center p-3 bg-slate-50 rounded-xl border border-slate-100">
              <div className="flex items-center gap-3">
                <Shield className="w-5 h-5 text-slate-400" />
                <span className="text-sm font-semibold text-slate-700">Status</span>
              </div>
              <span className={`px-2.5 py-1 rounded-full text-xs font-bold ${
                securityData?.account_info?.status === "Active" ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"
              }`}>
                {securityData?.account_info?.status || "Unknown"}
              </span>
            </div>
          </div>
        </motion.div>

        {/* Security Information */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden"
        >
          <div className="p-6 border-b border-slate-100 flex items-center gap-3">
            <div className="p-2 bg-purple-50 text-purple-600 rounded-xl">
              <Activity className="w-5 h-5" />
            </div>
            <h2 className="text-lg font-bold text-slate-800">Recent Activity</h2>
          </div>
          <div className="p-6 space-y-4">
            <div className="flex justify-between items-center p-3 bg-slate-50 rounded-xl border border-slate-100">
              <div className="flex items-center gap-3">
                <Clock className="w-5 h-5 text-slate-400" />
                <span className="text-sm font-semibold text-slate-700">Last Login</span>
              </div>
              <span className="text-sm font-medium text-slate-600">
                {securityData?.security_info?.last_login ? new Date(securityData.security_info.last_login).toLocaleString() : "N/A"}
              </span>
            </div>
            
            <div className="flex justify-between items-center p-3 bg-slate-50 rounded-xl border border-slate-100">
              <div className="flex items-center gap-3">
                <Laptop className="w-5 h-5 text-slate-400" />
                <span className="text-sm font-semibold text-slate-700">Active Sessions</span>
              </div>
              <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-cyan-100 text-cyan-700 text-xs font-bold">
                {securityData?.security_info?.active_sessions || 1}
              </span>
            </div>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
