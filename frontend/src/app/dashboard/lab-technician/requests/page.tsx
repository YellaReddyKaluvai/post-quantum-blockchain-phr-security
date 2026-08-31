"use client";

import React, { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
import { Search, ClipboardList, CheckCircle, Clock, PlayCircle, AlertTriangle, FileText } from "lucide-react";
import { getLabTestRequests, updateLabTestRequestStatus } from "@/lib/session";

interface TestRequestItem {
  id: string;
  patient_id: string;
  patient_name?: string;
  patient_user_id?: string;
  doctor_id?: string;
  doctor_name?: string;
  doctor_user_id?: string;
  test_name: string;
  panel_code?: string;
  priority: string;
  status: string;
  clinical_notes?: string;
  requested_date?: string;
  report_id?: string;
  report_no?: string;
}

export default function RequestsPage() {
  const [requests, setRequests] = useState<TestRequestItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);

  const fetchRequests = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const data = await getLabTestRequests();
      setRequests(data);
    } catch (error) {
      console.error(error);
      setLoadError("Could not load test requests from the server. Please retry.");
      setRequests([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchRequests();
  }, [fetchRequests]);

  const handleAccept = async (id: string) => {
    setBusyId(id);
    try {
      await updateLabTestRequestStatus(id, "Accepted");
      setRequests((prev) => prev.map((req) => (req.id === id ? { ...req, status: "Accepted" } : req)));
    } catch (e) {
      console.error(e);
      alert(e instanceof Error ? e.message : "Failed to accept the request");
    } finally {
      setBusyId(null);
    }
  };

  const getPriorityColor = (priority: string) => {
    if (priority === "Emergency") return "bg-rose-100 text-rose-700 border-rose-200";
    if (priority === "Urgent") return "bg-amber-100 text-amber-700 border-amber-200";
    return "bg-slate-100 text-slate-700 border-slate-200";
  };

  const getStatusColor = (status: string) => {
    if (status === "Completed") return "bg-emerald-100 text-emerald-700 border-emerald-200";
    if (status === "Accepted" || status === "In Progress") return "bg-blue-100 text-blue-700 border-blue-200";
    return "bg-slate-100 text-slate-700 border-slate-200";
  };

  const filteredRequests = requests.filter((req) => {
    const q = searchTerm.toLowerCase();
    return (
      (req.patient_name || "").toLowerCase().includes(q) ||
      (req.patient_user_id || "").toLowerCase().includes(q) ||
      (req.test_name || "").toLowerCase().includes(q)
    );
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Test Requests</h1>
          <p className="text-sm text-slate-500">Accept incoming requests and file the corresponding report.</p>
        </div>
      </div>

      <div className="bg-white/80 backdrop-blur-md rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
        <div className="p-4 border-b border-slate-100 bg-slate-50/50">
          <div className="relative max-w-md w-full">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              type="text"
              placeholder="Search by patient, ID, or test..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-9 pr-4 py-2 bg-white border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500/20 focus:border-cyan-500 transition-all"
            />
          </div>
        </div>

        {loadError && (
          <div className="m-4 flex items-center gap-2 px-4 py-3 bg-rose-50 border border-rose-100 rounded-xl text-sm text-rose-700">
            <AlertTriangle className="w-4 h-4 flex-shrink-0" />
            {loadError}
            <button onClick={fetchRequests} className="ml-auto font-semibold underline">Retry</button>
          </div>
        )}

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-100">
                <th className="px-6 py-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">Patient</th>
                <th className="px-6 py-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">Doctor</th>
                <th className="px-6 py-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">Test Details</th>
                <th className="px-6 py-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">Priority</th>
                <th className="px-6 py-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">Status</th>
                <th className="px-6 py-4 text-xs font-semibold text-slate-500 uppercase tracking-wider text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                [1, 2, 3].map((i) => (
                  <tr key={i}>
                    <td colSpan={6} className="px-6 py-4">
                      <div className="h-12 bg-slate-100 rounded-lg animate-pulse" />
                    </td>
                  </tr>
                ))
              ) : filteredRequests.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-8 text-center text-slate-500">
                    <ClipboardList className="w-12 h-12 mx-auto text-slate-300 mb-3" />
                    <p>No test requests found.</p>
                  </td>
                </tr>
              ) : (
                filteredRequests.map((req, idx) => (
                  <motion.tr
                    key={req.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: idx * 0.05 }}
                    className="hover:bg-slate-50/50 transition-colors group"
                  >
                    <td className="px-6 py-4">
                      <p className="font-semibold text-slate-800">{req.patient_name || "Patient"}</p>
                      <p className="text-xs text-slate-500">{req.patient_user_id}</p>
                    </td>
                    <td className="px-6 py-4">
                      <p className="text-sm font-medium text-slate-700">{req.doctor_name ? `Dr. ${req.doctor_name}` : "Dr. Unassigned"}</p>
                      <p className="text-xs text-slate-500">{req.doctor_user_id}</p>
                    </td>
                    <td className="px-6 py-4">
                      <p className="text-sm font-semibold text-slate-800">{req.test_name}</p>
                      <p className="text-xs text-slate-500">
                        {req.requested_date ? new Date(req.requested_date).toLocaleString() : ""}
                      </p>
                    </td>
                    <td className="px-6 py-4">
                      <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${getPriorityColor(req.priority)}`}>
                        {req.priority}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${getStatusColor(req.status)}`}>
                        {req.status === "Pending" && <Clock className="w-3.5 h-3.5" />}
                        {(req.status === "Accepted" || req.status === "In Progress") && <PlayCircle className="w-3.5 h-3.5" />}
                        {req.status === "Completed" && <CheckCircle className="w-3.5 h-3.5" />}
                        {req.status}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex justify-end gap-2">
                        {req.status === "Pending" && (
                          <button
                            onClick={() => handleAccept(req.id)}
                            disabled={busyId === req.id}
                            className="px-3 py-1.5 bg-blue-50 text-blue-600 hover:bg-blue-100 disabled:opacity-50 rounded-lg text-xs font-semibold transition-colors"
                          >
                            {busyId === req.id ? "Accepting…" : "Accept"}
                          </button>
                        )}
                        {(req.status === "Accepted" || req.status === "In Progress") && (
                          <button
                            onClick={() => (window.location.href = `/dashboard/lab-technician/create-report?reqId=${req.id}`)}
                            className="px-3 py-1.5 bg-emerald-50 text-emerald-600 hover:bg-emerald-100 rounded-lg text-xs font-semibold transition-colors"
                          >
                            Fill Report
                          </button>
                        )}
                        {req.status === "Completed" && req.report_no && (
                          <span className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold text-slate-500">
                            <FileText className="w-3.5 h-3.5" /> {req.report_no}
                          </span>
                        )}
                      </div>
                    </td>
                  </motion.tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
