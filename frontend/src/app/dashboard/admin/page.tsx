"use client";

import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  Users,
  Heart,
  Stethoscope,
  Syringe,
  FlaskConical,
  Clock,
  CheckCircle2,
  XCircle,
  Ban,
  Activity,
  UserPlus,
  Check,
  X,
  Loader2,
} from "lucide-react";
import {
  getDashboardStats,
  getRecentActivity,
  getAdminPending,
  approveRegistration,
  rejectRegistration,
} from "@/lib/session";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */
interface DashStats {
  total_users: number;
  patients: number;
  doctors: number;
  nurses: number;
  lab_technicians: number;
  pending_registrations: number;
  approved_registrations: number;
  rejected_registrations: number;
  disabled_users: number;
}

interface ActivityItem {
  id: string;
  action: string;
  admin_user_id?: string;
  target_public_user_id?: string;
  details?: unknown;
  created_at?: string;
}

interface PendingItem {
  id: string;
  full_name: string;
  email: string;
  role: string;
  date_of_birth?: string;
  blood_group?: string;
  specialization?: string;
}

/* ------------------------------------------------------------------ */
/*  Stat Card Config                                                   */
/* ------------------------------------------------------------------ */
const statCards: {
  key: keyof DashStats;
  label: string;
  icon: React.ElementType;
  gradient: string;
  iconBg: string;
  iconColor: string;
}[] = [
  { key: "total_users", label: "Total Users", icon: Users, gradient: "from-blue-50 to-blue-100/50", iconBg: "bg-blue-100", iconColor: "text-blue-600" },
  { key: "patients", label: "Patients", icon: Heart, gradient: "from-cyan-50 to-cyan-100/50", iconBg: "bg-cyan-100", iconColor: "text-cyan-600" },
  { key: "doctors", label: "Doctors", icon: Stethoscope, gradient: "from-teal-50 to-teal-100/50", iconBg: "bg-teal-100", iconColor: "text-teal-600" },
  { key: "nurses", label: "Nurses", icon: Syringe, gradient: "from-emerald-50 to-emerald-100/50", iconBg: "bg-emerald-100", iconColor: "text-emerald-600" },
  { key: "lab_technicians", label: "Lab Technicians", icon: FlaskConical, gradient: "from-violet-50 to-violet-100/50", iconBg: "bg-violet-100", iconColor: "text-violet-600" },
  { key: "pending_registrations", label: "Pending Requests", icon: Clock, gradient: "from-amber-50 to-amber-100/50", iconBg: "bg-amber-100", iconColor: "text-amber-600" },
  { key: "approved_registrations", label: "Approved", icon: CheckCircle2, gradient: "from-green-50 to-green-100/50", iconBg: "bg-green-100", iconColor: "text-green-600" },
  { key: "rejected_registrations", label: "Rejected", icon: XCircle, gradient: "from-rose-50 to-rose-100/50", iconBg: "bg-rose-100", iconColor: "text-rose-600" },
  { key: "disabled_users", label: "Disabled", icon: Ban, gradient: "from-gray-50 to-gray-100/50", iconBg: "bg-gray-200", iconColor: "text-gray-600" },
];

/* ------------------------------------------------------------------ */
/*  Skeleton helpers                                                   */
/* ------------------------------------------------------------------ */
function StatSkeleton() {
  return (
    <div className="rounded-2xl border border-slate-100 bg-white p-5 animate-pulse">
      <div className="flex items-center gap-4">
        <div className="w-12 h-12 rounded-xl bg-slate-100" />
        <div className="flex-1 space-y-2">
          <div className="h-3 w-20 bg-slate-100 rounded" />
          <div className="h-7 w-12 bg-slate-100 rounded" />
        </div>
      </div>
    </div>
  );
}

function ListSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-14 bg-slate-50 rounded-xl animate-pulse" />
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Toast component                                                    */
/* ------------------------------------------------------------------ */
function Toast({ message, type, onClose }: { message: string; type: "success" | "error"; onClose: () => void }) {
  useEffect(() => {
    const t = setTimeout(onClose, 4000);
    return () => clearTimeout(t);
  }, [onClose]);

  return (
    <motion.div
      initial={{ opacity: 0, y: -40 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -40 }}
      className={`fixed top-6 left-1/2 -translate-x-1/2 z-[100] px-6 py-3 rounded-2xl shadow-lg text-sm font-bold flex items-center gap-2 ${
        type === "success"
          ? "bg-emerald-500 text-white shadow-emerald-200"
          : "bg-rose-500 text-white shadow-rose-200"
      }`}
    >
      {type === "success" ? <CheckCircle2 className="w-4 h-4" /> : <XCircle className="w-4 h-4" />}
      {message}
    </motion.div>
  );
}

/* ------------------------------------------------------------------ */
/*  Page                                                               */
/* ------------------------------------------------------------------ */
export default function AdminDashboardHome() {
  const [stats, setStats] = useState<DashStats | null>(null);
  const [activity, setActivity] = useState<ActivityItem[]>([]);
  const [pending, setPending] = useState<PendingItem[]>([]);
  const [loadingStats, setLoadingStats] = useState(true);
  const [loadingActivity, setLoadingActivity] = useState(true);
  const [loadingPending, setLoadingPending] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null);

  useEffect(() => {
    getDashboardStats()
      .then((data) => setStats(data))
      .catch(() => setStats(null))
      .finally(() => setLoadingStats(false));

    getRecentActivity()
      .then((data) => setActivity(Array.isArray(data) ? data : data.items || []))
      .catch(() => setActivity([]))
      .finally(() => setLoadingActivity(false));

    getAdminPending()
      .then((data) => setPending(Array.isArray(data) ? data.slice(0, 5) : []))
      .catch(() => setPending([]))
      .finally(() => setLoadingPending(false));
  }, []);

  const handleApprove = async (id: string) => {
    try {
      setActionLoading(id);
      const res = await approveRegistration(id);
      setToast({ 
        message: res.message || `Approved! User ID: ${res.user_id}`, 
        type: res.email_sent !== false ? "success" : "error" 
      });
      setPending((prev) => prev.filter((p) => p.id !== id));
      // Refresh stats
      getDashboardStats().then(setStats).catch(() => {});
    } catch (err: unknown) {
      setToast({ message: err instanceof Error ? err.message : "Failed to approve", type: "error" });
    } finally {
      setActionLoading(null);
    }
  };

  const handleReject = async (id: string) => {
    try {
      setActionLoading(id);
      const res = await rejectRegistration(id);
      setToast({ 
        message: res.message || "Registration rejected.", 
        type: res.email_sent !== false ? "success" : "error" 
      });
      setPending((prev) => prev.filter((p) => p.id !== id));
      getDashboardStats().then(setStats).catch(() => {});
    } catch (err: unknown) {
      setToast({ message: err instanceof Error ? err.message : "Failed to reject", type: "error" });
    } finally {
      setActionLoading(null);
    }
  };

  const containerVariants = {
    hidden: { opacity: 0 },
    show: { opacity: 1, transition: { staggerChildren: 0.06 } },
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    show: { opacity: 1, y: 0, transition: { duration: 0.4, ease: "easeOut" as const } },
  };

  return (
    <>
      {/* Toast */}
      {toast && <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />}

      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="mb-8"
      >
        <h2 className="text-2xl sm:text-3xl font-extrabold text-slate-800">Dashboard Overview</h2>
        <p className="text-sm text-slate-500 mt-1">Monitor system metrics, recent activity, and pending registrations.</p>
      </motion.div>

      {/* Stats Grid */}
      <motion.div
        variants={containerVariants}
        initial="hidden"
        animate="show"
        className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4 mb-8"
      >
        {loadingStats
          ? Array.from({ length: 9 }).map((_, i) => <StatSkeleton key={i} />)
          : statCards.map((card) => (
              <motion.div
                key={card.key}
                variants={itemVariants}
                className={`rounded-2xl border border-slate-100 bg-gradient-to-br ${card.gradient} p-5 shadow-sm hover:shadow-md transition-shadow`}
              >
                <div className="flex items-center gap-4">
                  <div className={`w-12 h-12 rounded-xl ${card.iconBg} flex items-center justify-center`}>
                    <card.icon className={`w-6 h-6 ${card.iconColor}`} />
                  </div>
                  <div>
                    <p className="text-xs font-bold text-slate-500 uppercase tracking-wide">{card.label}</p>
                    <p className="text-2xl font-black text-slate-800 mt-0.5">
                      {stats ? (stats[card.key] ?? 0) : "—"}
                    </p>
                  </div>
                </div>
              </motion.div>
            ))}
      </motion.div>

      {/* Two-Column Section */}
      <div className="grid lg:grid-cols-2 gap-6">
        {/* Recent Activity */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3, duration: 0.5 }}
          className="rounded-2xl border border-slate-100 bg-white shadow-sm overflow-hidden"
        >
          <div className="px-6 py-4 border-b border-slate-100 flex items-center gap-3">
            <Activity className="w-5 h-5 text-cyan-500" />
            <h3 className="font-extrabold text-slate-800">Recent Activity</h3>
          </div>
          <div className="p-5">
            {loadingActivity ? (
              <ListSkeleton rows={5} />
            ) : activity.length === 0 ? (
              <p className="text-center text-sm text-slate-400 py-8">No recent activity found.</p>
            ) : (
              <div className="space-y-3">
                {activity.slice(0, 8).map((item, idx) => (
                  <div
                    key={item.id || idx}
                    className="flex items-start gap-3 p-3 rounded-xl bg-slate-50/80 hover:bg-slate-100/80 transition-colors"
                  >
                    <div className="w-8 h-8 rounded-lg bg-cyan-100 flex items-center justify-center mt-0.5 flex-shrink-0">
                      <Activity className="w-4 h-4 text-cyan-600" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-bold text-slate-700 truncate">{item.action.replace(/_/g, " ")}</p>
                      <p className="text-xs text-slate-500 mt-0.5">
                        Target: {item.target_public_user_id || "N/A"} • Admin: {item.admin_user_id || "SYSTEM"}
                      </p>
                      {item.details !== undefined && item.details !== null && (
                        <p className="text-xs text-slate-400 mt-0.5 truncate">
                          {typeof item.details === "object" ? JSON.stringify(item.details) : String(item.details)}
                        </p>
                      )}
                    </div>
                    <span className="text-[10px] text-slate-400 font-medium whitespace-nowrap">
                      {item.created_at ? new Date(item.created_at).toLocaleDateString() : ""}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </motion.div>

        {/* Pending Registrations */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4, duration: 0.5 }}
          className="rounded-2xl border border-slate-100 bg-white shadow-sm overflow-hidden"
        >
          <div className="px-6 py-4 border-b border-slate-100 flex items-center gap-3">
            <UserPlus className="w-5 h-5 text-amber-500" />
            <h3 className="font-extrabold text-slate-800">Pending Registrations</h3>
            {pending.length > 0 && (
              <span className="ml-auto inline-flex items-center justify-center w-6 h-6 rounded-full bg-amber-100 text-amber-700 text-xs font-black">
                {pending.length}
              </span>
            )}
          </div>
          <div className="p-5">
            {loadingPending ? (
              <ListSkeleton rows={5} />
            ) : pending.length === 0 ? (
              <p className="text-center text-sm text-slate-400 py-8">No pending registrations.</p>
            ) : (
              <div className="space-y-3">
                {pending.map((p) => (
                  <div
                    key={p.id}
                    className="flex items-center gap-3 p-3 rounded-xl bg-slate-50/80 hover:bg-slate-100/80 transition-colors"
                  >
                    <div className="w-8 h-8 rounded-lg bg-amber-100 flex items-center justify-center flex-shrink-0">
                      <UserPlus className="w-4 h-4 text-amber-600" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-bold text-slate-700 truncate">{p.full_name}</p>
                      <p className="text-xs text-slate-500">{p.role} • {p.email}</p>
                    </div>
                    <div className="flex items-center gap-1.5 flex-shrink-0">
                      <button
                        onClick={() => handleApprove(p.id)}
                        disabled={actionLoading === p.id}
                        className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 hover:bg-emerald-500 hover:text-white flex items-center justify-center transition-colors disabled:opacity-50"
                        title="Approve"
                      >
                        {actionLoading === p.id ? (
                          <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                          <Check className="w-4 h-4" />
                        )}
                      </button>
                      <button
                        onClick={() => handleReject(p.id)}
                        disabled={actionLoading === p.id}
                        className="w-8 h-8 rounded-lg bg-rose-50 text-rose-600 hover:bg-rose-500 hover:text-white flex items-center justify-center transition-colors disabled:opacity-50"
                        title="Reject"
                      >
                        {actionLoading === p.id ? (
                          <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                          <X className="w-4 h-4" />
                        )}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </motion.div>
      </div>
    </>
  );
}
