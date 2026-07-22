"use client";

import React, { useEffect, useState, useMemo, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  UserPlus,
  Search,
  Check,
  X,
  Loader2,
  CheckCircle2,
  XCircle,
  Clock,
  AlertTriangle,
  ShieldCheck,
  KeyRound,
  Mail,
} from "lucide-react";
import {
  getAllRegistrations,
  getAdminPending,
  approveRegistration,
  rejectRegistration,
} from "@/lib/session";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */
interface Registration {
  id: string;
  full_name: string;
  email: string;
  role: string;
  gender?: string;
  date_of_birth?: string;
  blood_group?: string;
  specialization?: string;
  status: string;
  created_at?: string;
}

/* ------------------------------------------------------------------ */
/*  Status Badge                                                       */
/* ------------------------------------------------------------------ */
function StatusBadge({ status }: { status: string }) {
  const s = status.toLowerCase();
  const styles =
    s === "pending"
      ? "bg-amber-50 text-amber-700 border-amber-100"
      : s === "approved"
      ? "bg-green-50 text-green-700 border-green-100"
      : s === "rejected"
      ? "bg-rose-50 text-rose-700 border-rose-100"
      : "bg-slate-50 text-slate-600 border-slate-100";

  return (
    <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-[11px] font-bold border ${styles}`}>
      {s === "pending" && <Clock className="w-3 h-3 mr-1" />}
      {s === "approved" && <CheckCircle2 className="w-3 h-3 mr-1" />}
      {s === "rejected" && <XCircle className="w-3 h-3 mr-1" />}
      {status.charAt(0).toUpperCase() + status.slice(1).toLowerCase()}
    </span>
  );
}

/* ------------------------------------------------------------------ */
/*  Modal Component                                                    */
/* ------------------------------------------------------------------ */
function Modal({
  open,
  onClose,
  children,
}: {
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
}) {
  if (!open) return null;
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 bg-black/50 backdrop-blur-sm z-[100] flex items-center justify-center p-4"
          onClick={onClose}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.9, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.9, y: 20 }}
            transition={{ type: "spring", damping: 25, stiffness: 300 }}
            className="bg-white rounded-2xl shadow-2xl max-w-md w-full overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {children}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/* ------------------------------------------------------------------ */
/*  Toast                                                              */
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
      className={`fixed top-6 left-1/2 -translate-x-1/2 z-[110] px-6 py-3 rounded-2xl shadow-lg text-sm font-bold flex items-center gap-2 ${
        type === "success" ? "bg-emerald-500 text-white" : "bg-rose-500 text-white"
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
export default function RegistrationsPage() {
  const [registrations, setRegistrations] = useState<Registration[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<"pending" | "all">("pending");
  const [roleFilter, setRoleFilter] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null);

  // Approve modal
  const [approveTarget, setApproveTarget] = useState<Registration | null>(null);
  // Reject modal
  const [rejectTarget, setRejectTarget] = useState<Registration | null>(null);
  const [rejectReason, setRejectReason] = useState("");

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      if (tab === "pending") {
        const data = await getAdminPending();
        setRegistrations(
          (Array.isArray(data) ? data : []).map((d: Registration) => ({ ...d, status: d.status || "Pending" }))
        );
      } else {
        const data = await getAllRegistrations();
        setRegistrations(Array.isArray(data) ? data : data.items || []);
      }
    } catch {
      setRegistrations([]);
    } finally {
      setLoading(false);
    }
  }, [tab]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const filtered = useMemo(() => {
    return registrations.filter((r) => {
      if (roleFilter && r.role.toLowerCase() !== roleFilter.toLowerCase()) return false;
      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        return (
          r.full_name.toLowerCase().includes(q) ||
          r.email.toLowerCase().includes(q) ||
          (r.id && r.id.toLowerCase().includes(q))
        );
      }
      return true;
    });
  }, [registrations, roleFilter, searchQuery]);

  /* ---- Actions ---- */
  const confirmApprove = async () => {
    if (!approveTarget) return;
    try {
      setActionLoading(approveTarget.id);
      const res = await approveRegistration(approveTarget.id);
      setToast({ 
        message: res.message || `Approved! User ID: ${res.user_id}`, 
        type: res.email_sent !== false ? "success" : "error" 
      });
      setApproveTarget(null);
      fetchData();
    } catch (err: unknown) {
      setToast({ message: err instanceof Error ? err.message : "Approval failed", type: "error" });
    } finally {
      setActionLoading(null);
    }
  };

  const confirmReject = async () => {
    if (!rejectTarget) return;
    try {
      setActionLoading(rejectTarget.id);
      const res = await rejectRegistration(rejectTarget.id, rejectReason || undefined);
      setToast({ 
        message: res.message || "Registration rejected.", 
        type: res.email_sent !== false ? "success" : "error" 
      });
      setRejectTarget(null);
      setRejectReason("");
      fetchData();
    } catch (err: unknown) {
      setToast({ message: err instanceof Error ? err.message : "Rejection failed", type: "error" });
    } finally {
      setActionLoading(null);
    }
  };

  const selectClass =
    "px-3 py-2.5 rounded-xl border border-slate-200 bg-white text-sm font-semibold text-slate-700 focus:outline-none focus:border-cyan-400 focus:ring-2 focus:ring-cyan-100 transition-all";

  return (
    <>
      {/* Toast */}
      {toast && <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />}

      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
        <div className="flex items-center gap-3 mb-1">
          <UserPlus className="w-7 h-7 text-cyan-500" />
          <h2 className="text-2xl sm:text-3xl font-extrabold text-slate-800">Registration Requests</h2>
        </div>
        <p className="text-sm text-slate-500">Review, approve, or reject incoming user registrations.</p>
      </motion.div>

      {/* Tabs */}
      <div className="flex gap-1 mb-5 bg-slate-100 rounded-xl p-1 w-fit">
        {(["pending", "all"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-5 py-2 rounded-lg text-sm font-bold transition-all ${
              tab === t ? "bg-white text-cyan-700 shadow-sm" : "text-slate-500 hover:text-slate-700"
            }`}
          >
            {t === "pending" ? "Pending" : "All Registrations"}
          </button>
        ))}
      </div>

      {/* Filters */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="flex flex-wrap gap-3 mb-6"
      >
        <select
          value={roleFilter}
          onChange={(e) => setRoleFilter(e.target.value)}
          className={selectClass}
        >
          <option value="">All Roles</option>
          <option value="Patient">Patient</option>
          <option value="Doctor">Doctor</option>
          <option value="Nurse">Nurse</option>
          <option value="Lab Technician">Lab Technician</option>
        </select>
        <div className="relative flex-1 min-w-[200px] max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            placeholder="Search by name or email..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-slate-200 bg-white text-sm font-semibold text-slate-700 focus:outline-none focus:border-cyan-400 focus:ring-2 focus:ring-cyan-100 transition-all placeholder:text-slate-400"
          />
        </div>
      </motion.div>

      {/* Table */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="rounded-2xl border border-slate-100 bg-white shadow-sm overflow-hidden"
      >
        <div className="overflow-x-auto">
          {loading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="w-8 h-8 text-cyan-500 animate-spin" />
            </div>
          ) : filtered.length === 0 ? (
            <div className="text-center py-20 text-slate-400">
              <UserPlus className="w-10 h-10 mx-auto mb-3 text-slate-300" />
              <p className="font-bold">No registrations found.</p>
            </div>
          ) : (
            <table className="w-full text-left border-collapse min-w-[900px]">
              <thead>
                <tr className="text-[11px] uppercase tracking-wider text-slate-500 border-b border-slate-100 bg-slate-50/60">
                  <th className="px-5 py-3 font-bold">Full Name</th>
                  <th className="px-5 py-3 font-bold">Email</th>
                  <th className="px-5 py-3 font-bold">Role</th>
                  <th className="px-5 py-3 font-bold">Gender</th>
                  <th className="px-5 py-3 font-bold">DOB</th>
                  <th className="px-5 py-3 font-bold">Registered</th>
                  <th className="px-5 py-3 font-bold">Status</th>
                  <th className="px-5 py-3 font-bold text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {filtered.map((reg) => (
                  <tr key={reg.id} className="hover:bg-slate-50/50 transition-colors">
                    <td className="px-5 py-4">
                      <div className="font-bold text-slate-800">{reg.full_name}</div>
                      {reg.blood_group && (
                        <span className="text-[10px] font-bold text-rose-500">Blood: {reg.blood_group}</span>
                      )}
                      {reg.specialization && (
                        <span className="text-[10px] font-bold text-teal-500">Spec: {reg.specialization}</span>
                      )}
                    </td>
                    <td className="px-5 py-4 text-sm text-slate-600">{reg.email}</td>
                    <td className="px-5 py-4">
                      <span className="inline-flex px-2.5 py-1 rounded-full text-[11px] font-bold bg-cyan-50 text-cyan-700 border border-cyan-100">
                        {reg.role}
                      </span>
                    </td>
                    <td className="px-5 py-4 text-sm text-slate-600">{reg.gender || "—"}</td>
                    <td className="px-5 py-4 text-sm text-slate-600">{reg.date_of_birth || "Encrypted"}</td>
                    <td className="px-5 py-4 text-xs text-slate-500">
                      {reg.created_at ? new Date(reg.created_at).toLocaleDateString() : "—"}
                    </td>
                    <td className="px-5 py-4">
                      <StatusBadge status={reg.status} />
                    </td>
                    <td className="px-5 py-4 text-right">
                      {reg.status.toLowerCase() === "pending" && (
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => setApproveTarget(reg)}
                            disabled={actionLoading === reg.id}
                            className="px-3 py-1.5 rounded-lg bg-emerald-50 text-emerald-700 text-xs font-bold hover:bg-emerald-500 hover:text-white transition-colors disabled:opacity-50"
                          >
                            Approve
                          </button>
                          <button
                            onClick={() => setRejectTarget(reg)}
                            disabled={actionLoading === reg.id}
                            className="px-3 py-1.5 rounded-lg bg-rose-50 text-rose-700 text-xs font-bold hover:bg-rose-500 hover:text-white transition-colors disabled:opacity-50"
                          >
                            Reject
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </motion.div>

      {/* Approve Modal */}
      <Modal open={!!approveTarget} onClose={() => setApproveTarget(null)}>
        <div className="p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-xl bg-emerald-100 flex items-center justify-center">
              <CheckCircle2 className="w-5 h-5 text-emerald-600" />
            </div>
            <h3 className="text-lg font-extrabold text-slate-800">Approve Registration?</h3>
          </div>
          <p className="text-sm text-slate-600 mb-4">
            Approving <span className="font-bold">{approveTarget?.full_name}</span> will:
          </p>
          <ul className="space-y-2 mb-6">
            {[
              { icon: ShieldCheck, text: "Generate the official User ID" },
              { icon: KeyRound, text: "Generate PQC credentials (ML-KEM & ML-DSA)" },
              { icon: CheckCircle2, text: "Activate the account" },
              { icon: Mail, text: "Send the approval email" },
            ].map(({ icon: Icon, text }) => (
              <li key={text} className="flex items-center gap-2 text-sm text-slate-700">
                <Icon className="w-4 h-4 text-emerald-500 flex-shrink-0" />
                {text}
              </li>
            ))}
          </ul>
          <div className="flex gap-3 justify-end">
            <button
              onClick={() => setApproveTarget(null)}
              className="px-5 py-2.5 rounded-xl text-sm font-bold text-slate-600 bg-slate-100 hover:bg-slate-200 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={confirmApprove}
              disabled={actionLoading === approveTarget?.id}
              className="px-5 py-2.5 rounded-xl text-sm font-bold text-white bg-emerald-500 hover:bg-emerald-600 transition-colors disabled:opacity-50 flex items-center gap-2"
            >
              {actionLoading === approveTarget?.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
              Approve
            </button>
          </div>
        </div>
      </Modal>

      {/* Reject Modal */}
      <Modal open={!!rejectTarget} onClose={() => { setRejectTarget(null); setRejectReason(""); }}>
        <div className="p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-xl bg-rose-100 flex items-center justify-center">
              <AlertTriangle className="w-5 h-5 text-rose-600" />
            </div>
            <h3 className="text-lg font-extrabold text-slate-800">Reject Registration?</h3>
          </div>
          <p className="text-sm text-slate-600 mb-4">
            Rejecting <span className="font-bold">{rejectTarget?.full_name}</span>. Provide an optional reason:
          </p>
          <textarea
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            placeholder="Optional rejection reason..."
            rows={3}
            className="w-full px-4 py-3 rounded-xl border border-slate-200 text-sm font-medium text-slate-700 focus:outline-none focus:border-rose-400 focus:ring-2 focus:ring-rose-100 transition-all resize-none placeholder:text-slate-400 mb-5"
          />
          <div className="flex gap-3 justify-end">
            <button
              onClick={() => { setRejectTarget(null); setRejectReason(""); }}
              className="px-5 py-2.5 rounded-xl text-sm font-bold text-slate-600 bg-slate-100 hover:bg-slate-200 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={confirmReject}
              disabled={actionLoading === rejectTarget?.id}
              className="px-5 py-2.5 rounded-xl text-sm font-bold text-white bg-rose-500 hover:bg-rose-600 transition-colors disabled:opacity-50 flex items-center gap-2"
            >
              {actionLoading === rejectTarget?.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <X className="w-4 h-4" />}
              Reject
            </button>
          </div>
        </div>
      </Modal>
    </>
  );
}
