"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ShieldCheck,
  Activity,
  Users,
  Settings,
  BellRing,
  Search,
  FileText,
  AlertTriangle,
  Fingerprint,
  Link as LinkIcon
} from "lucide-react";

export default function Home() {
  const [activeTab, setActiveTab] = useState("dashboard");

  return (
    <div className="min-h-screen bg-[var(--color-background-dark)] text-slate-100 flex overflow-hidden">

      {/* Animated Background Elements */}
      <div className="fixed inset-0 z-0 overflow-hidden pointer-events-none">
        <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] rounded-full bg-blue-600/20 blur-[120px]" style={{ animation: "float 15s ease-in-out infinite" }} />
        <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] rounded-full bg-violet-600/20 blur-[120px]" style={{ animation: "float 18s ease-in-out infinite reverse" }} />
        <div className="absolute top-[40%] left-[60%] w-[30%] h-[30%] rounded-full bg-emerald-600/10 blur-[100px]" style={{ animation: "float 20s ease-in-out infinite" }} />
      </div>

      {/* Sidebar Navigation */}
      <motion.aside
        initial={{ x: -100, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        className="w-20 lg:w-64 flex-shrink-0 z-10 glass-panel border-r border-slate-700/50 hidden md:flex flex-col"
      >
        <div className="h-20 flex items-center justify-center lg:justify-start lg:px-6 border-b border-slate-700/50">
          <ShieldCheck className="w-8 h-8 text-blue-400" />
          <span className="ml-3 font-bold text-xl tracking-wider hidden lg:block bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-violet-400">
            NexusPHR
          </span>
        </div>

        <nav className="flex-1 py-8 flex flex-col gap-2 px-4">
          <NavItem icon={<Activity />} label="Dashboard" active={activeTab === "dashboard"} onClick={() => setActiveTab("dashboard")} />
          <NavItem icon={<FileText />} label="Health Records" active={activeTab === "records"} onClick={() => setActiveTab("records")} />
          <NavItem icon={<Users />} label="Consent Mgmt" active={activeTab === "consent"} onClick={() => setActiveTab("consent")} />
          <NavItem icon={<Fingerprint />} label="Audit Logs" active={activeTab === "audit"} onClick={() => setActiveTab("audit")} />
        </nav>

        <div className="p-4 border-t border-slate-700/50">
          <NavItem icon={<Settings />} label="Settings" active={false} onClick={() => { }} />
        </div>
      </motion.aside>

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col z-10 overflow-hidden relative">

        {/* Top Header */}
        <header className="h-20 glass-panel border-b border-slate-700/50 flex items-center justify-between px-8">
          <div className="flex items-center glass-card px-4 py-2 rounded-full w-64 lg:w-96">
            <Search className="w-4 h-4 text-slate-400 mr-2" />
            <input
              type="text"
              placeholder="Search records or hashes..."
              className="bg-transparent border-none outline-none text-sm w-full text-slate-200 placeholder:text-slate-500"
            />
          </div>

          <div className="flex items-center gap-6">
            <button className="relative p-2 rounded-full hover:bg-slate-800 transition-colors">
              <BellRing className="w-5 h-5 text-slate-300" />
              <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
            </button>
            <div className="flex items-center gap-3 pl-6 border-l border-slate-700/50">
              <div className="w-9 h-9 rounded-full bg-gradient-to-br from-blue-500 to-violet-600 flex items-center justify-center font-bold text-sm shadow-lg">
                DR
              </div>
              <div className="hidden lg:block hidden">
                <p className="text-sm font-medium">Dr. Smith</p>
                <p className="text-xs text-slate-400">Cardiologist</p>
              </div>
            </div>
          </div>
        </header>

        {/* Scrollable Dashboard view */}
        <div className="flex-1 overflow-y-auto p-8 custom-scrollbar">

          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.4 }}
            className="max-w-7xl mx-auto space-y-8"
          >
            {/* Header Area */}
            <div className="flex justify-between items-end">
              <div>
                <h1 className="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-100 to-slate-300 mb-2">
                  System Overview
                </h1>
                <p className="text-slate-400">Post-Quantum Secured Health Data Platform</p>
              </div>

              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                className="bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/30 px-6 py-2 rounded-lg flex items-center gap-2 font-medium transition-all shadow-[0_0_15px_rgba(239,68,68,0.15)]"
              >
                <AlertTriangle className="w-4 h-4" />
                Break-Glass Access
              </motion.button>
            </div>

            {/* Quick Stats Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
              <StatCard title="Active PQC Keys" value="1,204" icon={<ShieldCheck />} color="blue" trend="+12% this week" />
              <StatCard title="Encrypted Records" value="45.2K" icon={<FileText />} color="violet" trend="+84 today" />
              <StatCard title="Immutable Logs" value="892K" icon={<LinkIcon />} color="emerald" trend="Synced 2m ago" />
              <StatCard title="AI Anomalies" value="0" icon={<Activity />} color="red" trend="Normal behavior" alert />
            </div>

            {/* Main Content Modules */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">

              {/* Recent Access Logs */}
              <div className="lg:col-span-2 glass-panel rounded-2xl p-6 relative overflow-hidden">
                <div className="absolute top-0 right-0 p-32 bg-blue-500/5 blur-[100px] rounded-full pointer-events-none" />

                <div className="flex justify-between items-center mb-6">
                  <h2 className="text-xl font-semibold flex items-center gap-2">
                    <Fingerprint className="w-5 h-5 text-blue-400" />
                    Live Audit Trail
                  </h2>
                  <span className="text-xs font-medium text-emerald-400 bg-emerald-400/10 px-3 py-1 rounded-full border border-emerald-400/20 flex items-center gap-1">
                    <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                    Blockchain Sync Active
                  </span>
                </div>

                <div className="space-y-4">
                  {[
                    { action: "Read_Record", user: "Dr. Sarah Jenkins", hash: "QmYw...x7A", time: "Just now", status: "success" },
                    { action: "Upload_Record", user: "Patient 8821", hash: "QmRx...p9B", time: "12 mins ago", status: "success" },
                    { action: "Grant_Consent", user: "Patient 4410", hash: "Dr. Michael Chen", time: "1 hour ago", status: "success" },
                    { action: "Read_Record", user: "Unknown Entity", hash: "QmZq...m2C", time: "2 hours ago", status: "denied" },
                  ].map((log, i) => (
                    <motion.div
                      initial={{ opacity: 0, x: -20 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.1 }}
                      key={i}
                      className="group flex items-center justify-between p-4 rounded-xl hover:bg-slate-800/50 border border-transparent hover:border-slate-700/50 transition-all cursor-pointer"
                    >
                      <div className="flex gap-4 items-center">
                        <div className={`p-2 rounded-lg ${log.status === 'success' ? 'bg-blue-500/10 text-blue-400' : 'bg-red-500/10 text-red-400'}`}>
                          {log.status === 'success' ? <ShieldCheck className="w-4 h-4" /> : <AlertTriangle className="w-4 h-4" />}
                        </div>
                        <div>
                          <p className="font-medium text-slate-200">{log.action}</p>
                          <p className="text-xs text-slate-500">{log.user}</p>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="text-sm font-mono text-slate-400 group-hover:text-blue-300 transition-colors">{log.hash}</p>
                        <p className="text-xs text-slate-500">{log.time}</p>
                      </div>
                    </motion.div>
                  ))}
                </div>
              </div>

              {/* System Security Status */}
              <div className="glass-panel rounded-2xl p-6 flex flex-col items-center justify-center text-center relative overflow-hidden">
                <div className="absolute inset-0 bg-gradient-to-b from-transparent to-black/20 z-0" />

                <h3 className="text-lg font-medium text-slate-300 z-10 mb-8 w-full text-left">PQC Encryption Layer</h3>

                <div className="relative w-48 h-48 flex items-center justify-center z-10 mb-6">
                  {/* Animated Rings */}
                  <motion.div
                    animate={{ rotate: 360 }}
                    transition={{ duration: 20, repeat: Infinity, ease: "linear" }}
                    className="absolute inset-0 border-2 border-dashed border-blue-500/30 rounded-full"
                  />
                  <motion.div
                    animate={{ rotate: -360 }}
                    transition={{ duration: 15, repeat: Infinity, ease: "linear" }}
                    className="absolute inset-4 border border-violet-500/40 rounded-full"
                  />

                  <div className="w-24 h-24 rounded-full bg-gradient-to-br from-blue-600 to-violet-600 flex items-center justify-center shadow-[0_0_30px_rgba(59,130,246,0.5)] z-20">
                    <ShieldCheck className="w-10 h-10 text-white" />
                  </div>
                </div>

                <div className="z-10 space-y-2">
                  <h4 className="font-semibold text-xl text-emerald-400 drop-shadow-[0_0_8px_rgba(16,185,129,0.5)]">CRYSTALS-Kyber Active</h4>
                  <p className="text-sm text-slate-400">Quantum-resistant state verified</p>
                </div>

                <div className="w-full mt-8 z-10 grid grid-cols-2 gap-4">
                  <div className="bg-slate-800/50 rounded-lg p-3 border border-slate-700/50">
                    <p className="text-xs text-slate-500 mb-1">Algorithm</p>
                    <p className="font-mono text-sm text-blue-300">Kyber-768</p>
                  </div>
                  <div className="bg-slate-800/50 rounded-lg p-3 border border-slate-700/50">
                    <p className="text-xs text-slate-500 mb-1">Symmetric wrapper</p>
                    <p className="font-mono text-sm text-violet-300">AES-256-GCM</p>
                  </div>
                </div>
              </div>

            </div>
          </motion.div>
        </div>
      </main>
    </div>
  );
}

// --- Helper Components ---

function NavItem({ icon, label, active, onClick }: { icon: React.ReactNode, label: string, active: boolean, onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-3 px-4 py-3 rounded-xl transition-all w-full text-left relative overflow-hidden group
        ${active ? 'text-blue-400 bg-blue-500/10' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'}`}
    >
      {active && (
        <motion.div
          layoutId="activeTabIndicator"
          className="absolute left-0 top-0 bottom-0 w-1 bg-blue-500 rounded-r-full"
        />
      )}
      <div className={`${active ? 'scale-110' : 'scale-100 group-hover:scale-110'} transition-transform duration-300`}>
        {icon}
      </div>
      <span className="font-medium text-sm hidden lg:block">{label}</span>
    </button>
  );
}

function StatCard({ title, value, icon, color, trend, alert = false }: any) {
  const colorMap: Record<string, string> = {
    blue: "from-blue-500/20 to-transparent text-blue-400 border-blue-500/20",
    violet: "from-violet-500/20 to-transparent text-violet-400 border-violet-500/20",
    emerald: "from-emerald-500/20 to-transparent text-emerald-400 border-emerald-500/20",
    red: "from-red-500/20 to-transparent text-red-400 border-red-500/20",
  };

  return (
    <motion.div
      whileHover={{ y: -5 }}
      className={`glass-card p-6 rounded-2xl relative overflow-hidden group`}
    >
      <div className={`absolute top-0 right-0 w-32 h-32 bg-gradient-to-br ${colorMap[color]} blur-2xl opacity-50 group-hover:opacity-100 transition-opacity`} />

      <div className="flex justify-between items-start mb-4 relative z-10">
        <div className={`p-3 rounded-xl bg-slate-800/80 backdrop-blur-sm border ${colorMap[color].split(' ')[3]}`}>
          {icon}
        </div>
        {alert && (
          <span className="flex h-3 w-3 relative">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
          </span>
        )}
      </div>

      <div className="relative z-10">
        <h3 className="text-slate-400 text-sm font-medium mb-1">{title}</h3>
        <p className="text-3xl font-bold text-slate-100 tracking-tight">{value}</p>
        <p className="text-xs text-slate-500 mt-2">{trend}</p>
      </div>
    </motion.div>
  );
}
