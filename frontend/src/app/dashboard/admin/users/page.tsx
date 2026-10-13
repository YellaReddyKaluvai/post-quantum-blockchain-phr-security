"use client";

import React, { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Users, Search, Loader2, Eye, ShieldAlert, ShieldCheck, ChevronLeft, ChevronRight, CheckCircle2, Clock, XCircle, Slash } from "lucide-react";
import { getAllUsers, disableUser, enableUser, getUserEmails, resendEmail } from "@/lib/session";

function StatusBadge({ status }: { status: string }) {
  const s = status.toLowerCase();
  const styles =
    s === "pending"
      ? "bg-amber-50 text-amber-700 border-amber-100"
      : s === "approved"
      ? "bg-emerald-50 text-emerald-700 border-emerald-100"
      : s === "rejected"
      ? "bg-rose-50 text-rose-700 border-rose-100"
      : s === "disabled"
      ? "bg-slate-100 text-slate-600 border-slate-200"
      : "bg-slate-50 text-slate-600 border-slate-100";

  return (
    <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-[11px] font-bold border ${styles}`}>
      {s === "pending" && <Clock className="w-3 h-3 mr-1" />}
      {s === "approved" && <CheckCircle2 className="w-3 h-3 mr-1" />}
      {s === "rejected" && <XCircle className="w-3 h-3 mr-1" />}
      {s === "disabled" && <Slash className="w-3 h-3 mr-1" />}
      {status.charAt(0).toUpperCase() + status.slice(1).toLowerCase()}
    </span>
  );
}

interface User {
  id: string;
  user_id?: string;
  full_name: string;
  email: string;
  role: string;
  status: string;
  gender?: string;
  created_at?: string;
  has_mlkem_keys?: boolean;
  has_mldsa_keys?: boolean;
}

interface UserEmail {
  id: string;
  notification_type: string;
  sent_status: string;
  email_subject: string;
  email_address: string;
  error_message?: string;
  created_at?: string;
}

export default function UsersPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  
  // Filters
  const [roleFilter, setRoleFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  
  // Pagination
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(10);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);

  // Modals
  const [detailUser, setDetailUser] = useState<User | null>(null);
  const [confirmDisable, setConfirmDisable] = useState<User | null>(null);
  
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null);

  const [userEmails, setUserEmails] = useState<UserEmail[]>([]);
  const [loadingEmails, setLoadingEmails] = useState(false);
  const [resendingEmailId, setResendingEmailId] = useState<string | null>(null);

  useEffect(() => {
    if (detailUser) {
      setLoadingEmails(true);
      getUserEmails(detailUser.id)
        .then((data) => setUserEmails(data))
        .catch(() => setUserEmails([]))
        .finally(() => setLoadingEmails(false));
    } else {
      setUserEmails([]);
    }
  }, [detailUser]);

  const handleResendEmail = async (notificationId: string) => {
    setResendingEmailId(notificationId);
    try {
      await resendEmail(notificationId);
      setToast({ message: "Email resent successfully", type: "success" });
      if (detailUser) {
        const data = await getUserEmails(detailUser.id);
        setUserEmails(data);
      }
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : "Failed to resend email";
      setToast({ message: errorMsg, type: "error" });
    } finally {
      setResendingEmailId(null);
    }
  };

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getAllUsers({
        role: roleFilter,
        status: statusFilter,
        search: searchQuery,
        page,
        per_page: perPage,
      });
      setUsers(data.users || []);
      setTotal(data.total || 0);
      setTotalPages(data.total_pages || 1);
    } catch {
      setToast({ message: "Failed to load users", type: "error" });
    } finally {
      setLoading(false);
    }
  }, [roleFilter, statusFilter, searchQuery, page, perPage]);

  // Debounced search trigger
  useEffect(() => {
    const t = setTimeout(() => {
      setPage(1); // Reset to page 1 on filter change
      fetchUsers();
    }, 300);
    return () => clearTimeout(t);
  }, [searchQuery, roleFilter, statusFilter, perPage, fetchUsers]);

  // Handle pagination changes (does not reset page)
  useEffect(() => {
    fetchUsers();
  }, [page, fetchUsers]);

  const handleDisable = async () => {
    if (!confirmDisable) return;
    try {
      setActionLoading(confirmDisable.id);
      await disableUser(confirmDisable.id);
      setToast({ message: "Account disabled successfully.", type: "success" });
      setConfirmDisable(null);
      fetchUsers();
    } catch (err: unknown) {
      setToast({ message: err instanceof Error ? err.message : "Failed to disable", type: "error" });
    } finally {
      setActionLoading(null);
    }
  };

  const handleEnable = async (id: string) => {
    try {
      setActionLoading(id);
      await enableUser(id);
      setToast({ message: "Account enabled successfully.", type: "success" });
      fetchUsers();
    } catch (err: unknown) {
      setToast({ message: err instanceof Error ? err.message : "Failed to enable", type: "error" });
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <>
      {toast && (
        <motion.div
          initial={{ opacity: 0, y: -40 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -40 }}
          className={`fixed top-6 left-1/2 -translate-x-1/2 z-[110] px-6 py-3 rounded-2xl shadow-lg text-sm font-bold flex items-center gap-2 ${
            toast.type === "success" ? "bg-emerald-500 text-white" : "bg-rose-500 text-white"
          }`}
          onClick={() => setToast(null)}
        >
          {toast.message}
        </motion.div>
      )}

      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
        <div className="flex items-center gap-3 mb-1">
          <Users className="w-7 h-7 text-cyan-500" />
          <h2 className="text-2xl sm:text-3xl font-extrabold text-slate-800">User Management</h2>
        </div>
        <p className="text-sm text-slate-500">View and manage all system identities across roles.</p>
      </motion.div>

      {/* Filters */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="flex flex-wrap gap-3 mb-6"
      >
        <select value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)} className="px-3 py-2.5 rounded-xl border border-slate-200 bg-white text-sm font-semibold text-slate-700 focus:outline-none focus:border-cyan-400 focus:ring-2 focus:ring-cyan-100 transition-all">
          <option value="">All Roles</option>
          <option value="Patient">Patient</option>
          <option value="Doctor">Doctor</option>
          <option value="Nurse">Nurse</option>
          <option value="Lab Technician">Lab Technician</option>
          <option value="Administrator">Administrator</option>
        </select>
        
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="px-3 py-2.5 rounded-xl border border-slate-200 bg-white text-sm font-semibold text-slate-700 focus:outline-none focus:border-cyan-400 focus:ring-2 focus:ring-cyan-100 transition-all">
          <option value="">All Statuses</option>
          <option value="Pending">Pending</option>
          <option value="Approved">Approved / Active</option>
          <option value="Rejected">Rejected</option>
          <option value="Disabled">Disabled</option>
        </select>

        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            placeholder="Search by ID, Name, or Email..."
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
        className="rounded-2xl border border-slate-100 bg-white shadow-sm overflow-hidden flex flex-col"
      >
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse min-w-[900px]">
            <thead>
              <tr className="text-[11px] uppercase tracking-wider text-slate-500 border-b border-slate-100 bg-slate-50/60">
                <th className="px-5 py-3 font-bold">User ID</th>
                <th className="px-5 py-3 font-bold">Full Name</th>
                <th className="px-5 py-3 font-bold">Role</th>
                <th className="px-5 py-3 font-bold">Status</th>
                <th className="px-5 py-3 font-bold">Registered</th>
                <th className="px-5 py-3 font-bold text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {loading ? (
                <tr>
                  <td colSpan={6} className="py-20 text-center">
                    <Loader2 className="w-8 h-8 text-cyan-500 animate-spin mx-auto" />
                  </td>
                </tr>
              ) : users.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-20 text-center text-slate-400">
                    <Users className="w-10 h-10 mx-auto mb-3 text-slate-300" />
                    <p className="font-bold">No users found.</p>
                  </td>
                </tr>
              ) : (
                users.map((u) => (
                  <tr key={u.id} className="hover:bg-slate-50/50 transition-colors">
                    <td className="px-5 py-4 font-mono text-sm font-bold text-slate-700">{u.user_id || "—"}</td>
                    <td className="px-5 py-4">
                      <div className="font-bold text-slate-800">{u.full_name}</div>
                      <div className="text-xs text-slate-500">{u.email}</div>
                    </td>
                    <td className="px-5 py-4">
                      <span className="inline-flex px-2.5 py-1 rounded-full text-[11px] font-bold bg-cyan-50 text-cyan-700 border border-cyan-100">
                        {u.role}
                      </span>
                    </td>
                    <td className="px-5 py-4">
                      <StatusBadge status={u.status} />
                    </td>
                    <td className="px-5 py-4 text-xs text-slate-500">
                      {u.created_at ? new Date(u.created_at).toLocaleDateString() : "—"}
                    </td>
                    <td className="px-5 py-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => setDetailUser(u)}
                          className="px-3 py-1.5 rounded-lg bg-slate-100 text-slate-700 text-xs font-bold hover:bg-slate-200 transition-colors flex items-center gap-1.5"
                        >
                          <Eye className="w-3.5 h-3.5" /> View
                        </button>
                        
                        {u.status === "Approved" && (
                          <button
                            onClick={() => setConfirmDisable(u)}
                            disabled={actionLoading === u.id}
                            className="px-3 py-1.5 rounded-lg bg-rose-50 text-rose-700 text-xs font-bold hover:bg-rose-500 hover:text-white transition-colors disabled:opacity-50 flex items-center gap-1.5"
                          >
                            <ShieldAlert className="w-3.5 h-3.5" /> Disable
                          </button>
                        )}
                        
                        {u.status === "Disabled" && (
                          <button
                            onClick={() => handleEnable(u.id)}
                            disabled={actionLoading === u.id}
                            className="px-3 py-1.5 rounded-lg bg-emerald-50 text-emerald-700 text-xs font-bold hover:bg-emerald-500 hover:text-white transition-colors disabled:opacity-50 flex items-center gap-1.5"
                          >
                            {actionLoading === u.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <ShieldCheck className="w-3.5 h-3.5" />}
                            Enable
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="p-4 border-t border-slate-100 bg-slate-50 flex items-center justify-between text-sm font-semibold text-slate-600">
          <div>
            Showing {users.length > 0 ? (page - 1) * perPage + 1 : 0} to {Math.min(page * perPage, total)} of {total} results
          </div>
          <div className="flex items-center gap-4">
            <select
              value={perPage}
              onChange={(e) => { setPerPage(Number(e.target.value)); setPage(1); }}
              className="px-2 py-1.5 rounded-lg border border-slate-200 bg-white"
            >
              <option value={10}>10 per page</option>
              <option value={25}>25 per page</option>
              <option value={50}>50 per page</option>
            </select>
            <div className="flex gap-1">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1}
                className="p-1.5 rounded-lg hover:bg-slate-200 disabled:opacity-30 transition-colors"
              >
                <ChevronLeft className="w-5 h-5" />
              </button>
              <span className="px-3 py-1.5 font-mono">{page} / {totalPages}</span>
              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="p-1.5 rounded-lg hover:bg-slate-200 disabled:opacity-30 transition-colors"
              >
                <ChevronRight className="w-5 h-5" />
              </button>
            </div>
          </div>
        </div>
      </motion.div>

      {/* Disable Confirm Modal */}
      <AnimatePresence>
        {confirmDisable && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/50 backdrop-blur-sm z-[100] flex items-center justify-center p-4"
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="bg-white rounded-2xl shadow-2xl max-w-sm w-full p-6"
            >
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-xl bg-rose-100 flex items-center justify-center text-rose-600">
                  <ShieldAlert className="w-5 h-5" />
                </div>
                <h3 className="text-lg font-extrabold text-slate-800">Disable Account?</h3>
              </div>
              <p className="text-sm text-slate-600 mb-6">
                Are you sure you want to disable access for <strong>{confirmDisable.full_name}</strong>? They will be instantly logged out and unable to authenticate until re-enabled.
              </p>
              <div className="flex gap-3 justify-end">
                <button
                  onClick={() => setConfirmDisable(null)}
                  className="px-4 py-2 rounded-xl text-sm font-bold text-slate-600 bg-slate-100 hover:bg-slate-200 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleDisable}
                  disabled={actionLoading === confirmDisable.id}
                  className="px-4 py-2 rounded-xl text-sm font-bold text-white bg-rose-500 hover:bg-rose-600 flex items-center gap-2 transition-colors disabled:opacity-50"
                >
                  {actionLoading === confirmDisable.id ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                  Disable Account
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Detail Modal */}
      <AnimatePresence>
        {detailUser && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/50 backdrop-blur-sm z-[100] flex items-center justify-center p-4"
            onClick={() => setDetailUser(null)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              className="bg-white rounded-2xl shadow-2xl max-w-lg w-full overflow-hidden"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="p-6 border-b border-slate-100 bg-slate-50/50 flex justify-between items-center">
                <h3 className="text-lg font-extrabold text-slate-800">User Details</h3>
                <button onClick={() => setDetailUser(null)} className="p-2 rounded-xl text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition-colors">
                  <XCircle className="w-5 h-5" />
                </button>
              </div>
              <div className="p-6 space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <div className="text-[10px] font-extrabold text-slate-400 uppercase tracking-widest mb-1">Full Name</div>
                    <div className="font-bold text-slate-800">{detailUser.full_name}</div>
                  </div>
                  <div>
                    <div className="text-[10px] font-extrabold text-slate-400 uppercase tracking-widest mb-1">User ID</div>
                    <div className="font-mono font-bold text-slate-700">{detailUser.user_id || "N/A"}</div>
                  </div>
                  <div>
                    <div className="text-[10px] font-extrabold text-slate-400 uppercase tracking-widest mb-1">Email</div>
                    <div className="font-semibold text-slate-600 text-sm">{detailUser.email}</div>
                  </div>
                  <div>
                    <div className="text-[10px] font-extrabold text-slate-400 uppercase tracking-widest mb-1">Status</div>
                    <div><StatusBadge status={detailUser.status} /></div>
                  </div>
                  <div>
                    <div className="text-[10px] font-extrabold text-slate-400 uppercase tracking-widest mb-1">Role</div>
                    <div className="font-semibold text-slate-700">{detailUser.role}</div>
                  </div>
                  <div>
                    <div className="text-[10px] font-extrabold text-slate-400 uppercase tracking-widest mb-1">Gender</div>
                    <div className="font-semibold text-slate-700">{detailUser.gender || "—"}</div>
                  </div>
                </div>
                
                <div className="pt-4 border-t border-slate-100">
                  <div className="text-[10px] font-extrabold text-slate-400 uppercase tracking-widest mb-3">System & Security Info</div>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="bg-slate-50 p-3 rounded-xl border border-slate-100">
                      <div className="text-xs text-slate-500 mb-1">PQC ML-KEM Keys</div>
                      <div className="font-bold text-slate-700">{detailUser.has_mlkem_keys ? "Generated" : "Pending"}</div>
                    </div>
                    <div className="bg-slate-50 p-3 rounded-xl border border-slate-100">
                      <div className="text-xs text-slate-500 mb-1">PQC ML-DSA Keys</div>
                      <div className="font-bold text-slate-700">{detailUser.has_mldsa_keys ? "Generated" : "Pending"}</div>
                    </div>
                  </div>
                </div>

                <div className="pt-4 border-t border-slate-100">
                  <div className="text-[10px] font-extrabold text-slate-400 uppercase tracking-widest mb-3">Email Notification Logs</div>
                  {loadingEmails ? (
                    <div className="flex items-center justify-center py-4">
                      <Loader2 className="w-5 h-5 text-cyan-500 animate-spin" />
                    </div>
                  ) : userEmails.length === 0 ? (
                    <p className="text-xs text-slate-400 italic">No email logs found for this user.</p>
                  ) : (
                    <div className="space-y-3 max-h-[180px] overflow-y-auto pr-1">
                      {userEmails.map((email) => (
                        <div key={email.id} className="p-3 bg-slate-50 rounded-xl border border-slate-100 flex flex-col gap-1.5">
                          <div className="flex items-center justify-between text-[11px] font-bold">
                            <span className="text-slate-600 uppercase">{email.notification_type}</span>
                            <span className={`px-2 py-0.5 rounded-full text-[9px] border uppercase ${
                              email.sent_status === 'SENT' ? 'bg-emerald-50 text-emerald-700 border-emerald-100' :
                              email.sent_status === 'FAILED' ? 'bg-rose-50 text-rose-700 border-rose-100' : 'bg-amber-50 text-amber-700 border-amber-100'
                            }`}>
                              {email.sent_status}
                            </span>
                          </div>
                          <div className="text-xs text-slate-700 font-semibold">{email.email_subject}</div>
                          <div className="text-[10px] text-slate-500 font-mono line-clamp-1">{email.email_address}</div>
                          {email.error_message && (
                            <div className="text-[10px] text-rose-600 bg-rose-50/50 p-2 rounded-lg border border-rose-100/50 break-words font-mono">
                              Error: {email.error_message}
                            </div>
                          )}
                          <div className="flex items-center justify-between mt-1">
                            <span className="text-[9px] text-slate-400 font-medium">
                              {email.created_at ? new Date(email.created_at).toLocaleString() : ''}
                            </span>
                            {email.sent_status === 'FAILED' && (
                              <button
                                onClick={() => handleResendEmail(email.id)}
                                disabled={resendingEmailId === email.id}
                                className="px-2.5 py-1 bg-cyan-50 text-cyan-700 hover:bg-cyan-500 hover:text-white rounded-lg text-[10px] font-extrabold transition-all border border-cyan-100 disabled:opacity-50 flex items-center gap-1"
                              >
                                {resendingEmailId === email.id ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
                                Resend Email
                              </button>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
