"use client";

import React, { useEffect, useState } from "react";
import { getAdminPending, approveRegistration, rejectRegistration } from "@/lib/session";
import type { PendingRegistration } from "@/lib/session";
import RoleDashboard from "@/components/RoleDashboard";
import { Check, X, Loader2 } from "lucide-react";

export default function AdminDashboardPage() {
  const [pending, setPending] = useState<PendingRegistration[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [message, setMessage] = useState<{type: "success" | "error", text: string} | null>(null);

  useEffect(() => {
    fetchPending();
  }, []);

  const fetchPending = async () => {
    try {
      const data = await getAdminPending();
      setPending(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async (id: string) => {
    try {
      setActionLoading(id);
      const res = await approveRegistration(id);
      setMessage({ type: "success", text: `Approved! User ID: ${res.user_id}` });
      await fetchPending();
    } catch (err: unknown) {
      setMessage({ type: "error", text: getErrorMessage(err, "Failed to approve") });
    } finally {
      setActionLoading(null);
    }
  };

  const handleReject = async (id: string) => {
    try {
      setActionLoading(id);
      await rejectRegistration(id);
      setMessage({ type: "success", text: "Registration rejected." });
      await fetchPending();
    } catch (err: unknown) {
      setMessage({ type: "error", text: getErrorMessage(err, "Failed to reject") });
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <RoleDashboard role="Administrator" title="Admin Verification" description="Manage incoming registration requests and provision quantum identities.">
      <div className="mt-8 bg-white rounded-3xl border border-slate-100 shadow-sm overflow-hidden">
        <div className="p-6 border-b border-slate-100 flex justify-between items-center bg-slate-50/50">
          <h3 className="font-black text-cyan-950 text-lg">Pending Verification ({pending.length})</h3>
        </div>
        
        {message && (
          <div className={`p-4 mx-6 mt-6 rounded-xl text-sm font-semibold toast-animate ${message.type === 'success' ? 'bg-emerald-50 text-emerald-700 border border-emerald-100' : 'bg-rose-50 text-rose-700 border border-rose-100'}`}>
            {message.text}
          </div>
        )}

        <div className="p-6 overflow-x-auto">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-8 h-8 text-cyan-500 animate-spin" />
            </div>
          ) : pending.length === 0 ? (
            <div className="text-center py-12 text-slate-500">No pending registrations found.</div>
          ) : (
            <table className="w-full text-left border-collapse min-w-[800px]">
              <thead>
                <tr className="text-xs uppercase tracking-wider text-slate-500 border-b border-slate-100">
                  <th className="pb-3 font-bold">Name / Email</th>
                  <th className="pb-3 font-bold">Role</th>
                  <th className="pb-3 font-bold">Details</th>
                  <th className="pb-3 font-bold text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {pending.map((p) => (
                  <tr key={p.id} className="hover:bg-slate-50/50 transition-colors">
                    <td className="py-4">
                      <div className="font-bold text-slate-800">{p.full_name}</div>
                      <div className="text-sm text-slate-500">{p.email}</div>
                    </td>
                    <td className="py-4">
                      <span className="inline-flex px-3 py-1 rounded-full text-xs font-bold bg-cyan-50 text-cyan-700 border border-cyan-100">
                        {p.role}
                      </span>
                    </td>
                    <td className="py-4 text-sm text-slate-600">
                      <div>DOB: {p.date_of_birth || "Encrypted"}</div>
                      {p.blood_group && <div>Blood: {p.blood_group}</div>}
                      {p.specialization && <div>Spec: {p.specialization}</div>}
                    </td>
                    <td className="py-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button 
                          onClick={() => handleApprove(p.id)}
                          disabled={actionLoading === p.id}
                          className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-emerald-50 text-emerald-600 hover:bg-emerald-500 hover:text-white transition-colors disabled:opacity-50"
                          title="Approve"
                        >
                          {actionLoading === p.id ? <Loader2 className="w-4 h-4 animate-spin"/> : <Check className="w-4 h-4" />}
                        </button>
                        <button 
                          onClick={() => handleReject(p.id)}
                          disabled={actionLoading === p.id}
                          className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-rose-50 text-rose-600 hover:bg-rose-500 hover:text-white transition-colors disabled:opacity-50"
                          title="Reject"
                        >
                          {actionLoading === p.id ? <Loader2 className="w-4 h-4 animate-spin"/> : <X className="w-4 h-4" />}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </RoleDashboard>
  );
}
  const getErrorMessage = (error: unknown, fallback: string) =>
    error instanceof Error ? error.message : fallback;
