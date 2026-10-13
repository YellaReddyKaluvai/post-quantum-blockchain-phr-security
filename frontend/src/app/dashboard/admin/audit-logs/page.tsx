"use client";

import React, { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
import { FileText, Loader2, ChevronLeft, ChevronRight, Filter } from "lucide-react";
import { getAuditLogs } from "@/lib/session";

interface AuditLog {
  id: string;
  created_at?: string;
  admin_user_id?: string;
  action: string;
  target_public_user_id?: string;
  details?: unknown;
}

export default function AuditLogsPage() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [actionFilter, setActionFilter] = useState("");
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(20);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getAuditLogs({ action: actionFilter, page, per_page: perPage });
      setLogs(data.logs || []);
      setTotal(data.total || 0);
      setTotalPages(data.total_pages || 1);
    } catch {
      setError("Failed to load audit logs");
    } finally {
      setLoading(false);
    }
  }, [actionFilter, page, perPage]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  const handleActionChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setActionFilter(e.target.value);
    setPage(1);
  };

  const formatAction = (action: string) => {
    return action.replace(/_/g, " ");
  };

  const getActionColor = (action: string) => {
    if (action.includes("APPROVED") || action.includes("ENABLED")) return "bg-emerald-50 text-emerald-700 border-emerald-100";
    if (action.includes("REJECTED") || action.includes("DISABLED")) return "bg-rose-50 text-rose-700 border-rose-100";
    if (action.includes("LOGIN") || action.includes("LOGOUT")) return "bg-cyan-50 text-cyan-700 border-cyan-100";
    return "bg-slate-50 text-slate-700 border-slate-200";
  };

  return (
    <>
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
        <div className="flex items-center gap-3 mb-1">
          <FileText className="w-7 h-7 text-cyan-500" />
          <h2 className="text-2xl sm:text-3xl font-extrabold text-slate-800">Audit Logs</h2>
        </div>
        <p className="text-sm text-slate-500">Immutable record of administrator actions and system changes.</p>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="flex flex-wrap gap-3 mb-6 items-center"
      >
        <div className="relative">
          <Filter className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <select
            value={actionFilter}
            onChange={handleActionChange}
            className="pl-9 pr-4 py-2.5 rounded-xl border border-slate-200 bg-white text-sm font-semibold text-slate-700 focus:outline-none focus:border-cyan-400 focus:ring-2 focus:ring-cyan-100 transition-all appearance-none min-w-[250px]"
          >
            <option value="">All Actions</option>
            <option value="REGISTRATION_APPROVED">Registration Approved</option>
            <option value="REGISTRATION_REJECTED">Registration Rejected</option>
            <option value="USER_DISABLED">User Disabled</option>
            <option value="USER_ENABLED">User Enabled</option>
            <option value="ADMIN_LOGIN">Admin Login</option>
            <option value="ADMIN_LOGOUT">Admin Logout</option>
          </select>
        </div>
      </motion.div>

      {error ? (
        <div className="p-6 bg-rose-50 border border-rose-100 rounded-2xl text-rose-600 font-bold text-center">
          {error}
        </div>
      ) : (
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
                  <th className="px-5 py-3 font-bold">Timestamp</th>
                  <th className="px-5 py-3 font-bold">Admin ID</th>
                  <th className="px-5 py-3 font-bold">Action</th>
                  <th className="px-5 py-3 font-bold">Target User</th>
                  <th className="px-5 py-3 font-bold">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {loading ? (
                  <tr>
                    <td colSpan={5} className="py-20 text-center">
                      <Loader2 className="w-8 h-8 text-cyan-500 animate-spin mx-auto" />
                    </td>
                  </tr>
                ) : logs.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="py-20 text-center text-slate-400">
                      <FileText className="w-10 h-10 mx-auto mb-3 text-slate-300" />
                      <p className="font-bold">No logs found.</p>
                    </td>
                  </tr>
                ) : (
                  logs.map((log) => (
                    <tr key={log.id} className="hover:bg-slate-50/50 transition-colors">
                      <td className="px-5 py-4 text-xs font-medium text-slate-500 whitespace-nowrap">
                        {log.created_at ? new Date(log.created_at).toLocaleString() : "—"}
                      </td>
                      <td className="px-5 py-4 font-mono text-sm font-bold text-slate-700">
                        {log.admin_user_id || "SYSTEM"}
                      </td>
                      <td className="px-5 py-4">
                        <span className={`inline-flex px-2.5 py-1 rounded-md text-[10px] font-bold border uppercase tracking-wider ${getActionColor(log.action)}`}>
                          {formatAction(log.action)}
                        </span>
                      </td>
                      <td className="px-5 py-4 font-mono text-sm font-bold text-slate-600">
                        {log.target_public_user_id || "—"}
                      </td>
                      <td className="px-5 py-4 text-xs text-slate-600 font-mono">
                        {log.details ? (
                          <pre className="m-0 bg-slate-50 p-2 rounded-md border border-slate-100 max-w-[300px] overflow-x-auto">
                            {JSON.stringify(log.details, null, 2)}
                          </pre>
                        ) : "—"}
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
              Showing {logs.length > 0 ? (page - 1) * perPage + 1 : 0} to {Math.min(page * perPage, total)} of {total} results
            </div>
            <div className="flex items-center gap-4">
              <select
                value={perPage}
                onChange={(e) => { setPerPage(Number(e.target.value)); setPage(1); }}
                className="px-2 py-1.5 rounded-lg border border-slate-200 bg-white"
              >
                <option value={20}>20 per page</option>
                <option value={50}>50 per page</option>
                <option value={100}>100 per page</option>
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
      )}
    </>
  );
}
