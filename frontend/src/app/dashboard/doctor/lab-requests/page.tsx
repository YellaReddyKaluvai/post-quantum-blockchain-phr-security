"use client";

import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import {
  FlaskConical, Clock, CheckCircle2, Loader2, AlertTriangle,
  FileCheck, User, ChevronRight,
} from "lucide-react";
import { getDoctorLabRequests, downloadDoctorLabReport } from "@/lib/session";

interface LabRequest {
  id: string;
  patient_id: string;
  patient_name?: string;
  patient_user_id?: string;
  test_name: string;
  panel_code?: string | null;
  priority: string;
  status: string;
  clinical_notes?: string | null;
  requested_date?: string | null;
  report_id?: string | null;
  report_no?: string | null;
}

// Mirrors the backend lab_request_status enum.
const STATUS_FILTERS = ["All", "Pending", "Accepted", "In Progress", "Completed"] as const;

const STATUS_STYLE: Record<string, string> = {
  Pending: "bg-amber-50 text-amber-700 border-amber-200",
  Accepted: "bg-blue-50 text-blue-700 border-blue-200",
  "In Progress": "bg-violet-50 text-violet-700 border-violet-200",
  Completed: "bg-emerald-50 text-emerald-700 border-emerald-200",
};

const PRIORITY_STYLE: Record<string, string> = {
  Emergency: "bg-rose-100 text-rose-700",
  Urgent: "bg-amber-100 text-amber-700",
  Routine: "bg-slate-100 text-slate-600",
};

export default function DoctorLabRequestsPage() {
  const [requests, setRequests] = useState<LabRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [filter, setFilter] = useState<string>("All");
  const [busyReport, setBusyReport] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      setRequests(await getDoctorLabRequests(filter === "All" ? undefined : filter));
    } catch (error) {
      console.error(error);
      setRequests([]);
      setLoadError("Could not load your test requests. Check that the backend is running.");
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  const openReport = async (reportId: string) => {
    setLoadError("");
    setBusyReport(reportId);
    try {
      const blob = await downloadDoctorLabReport(reportId);
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank", "noopener");
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "Could not open the report.");
    } finally {
      setBusyReport(null);
    }
  };

  // Counts come from the full list, so they stay meaningful while a filter is on.
  const awaiting = requests.filter((r) => r.status !== "Completed").length;

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-xl md:text-2xl font-bold text-slate-800">Lab Requests</h1>
        <p className="text-slate-500 mt-1">
          Investigations you have ordered, and where each one has got to.
        </p>
      </motion.div>

      {loadError && (
        <div className="p-3 rounded-xl bg-rose-50 border border-rose-100 text-rose-700 text-sm font-semibold">
          {loadError}
        </div>
      )}

      <div className="flex items-center gap-2 flex-wrap">
        {STATUS_FILTERS.map((s) => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className={`px-3.5 py-1.5 rounded-xl text-xs font-bold transition-colors border ${
              filter === s
                ? "bg-indigo-600 text-white border-indigo-600"
                : "bg-white text-slate-600 border-slate-200 hover:bg-slate-50"
            }`}
          >
            {s}
          </button>
        ))}
        {filter === "All" && awaiting > 0 && (
          <span className="ml-auto text-xs font-semibold text-slate-500">
            {awaiting} still awaiting results
          </span>
        )}
      </div>

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-28 bg-slate-200 animate-pulse rounded-2xl" />
          ))}
        </div>
      ) : requests.length === 0 ? (
        <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-12 text-center">
          <FlaskConical className="w-14 h-14 mx-auto text-slate-300 mb-4" />
          <h3 className="text-lg font-bold text-slate-700">
            {filter === "All" ? "No Tests Requested" : `Nothing ${filter}`}
          </h3>
          <p className="text-slate-500 mt-1">
            {filter === "All"
              ? "Open a patient's chart and use Request Lab Test to order an investigation."
              : "Try a different status filter."}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {requests.map((r, idx) => (
            <motion.div
              key={r.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.04 }}
              className="bg-white rounded-2xl shadow-sm border border-slate-100 p-5"
            >
              <div className="flex flex-col lg:flex-row lg:items-center gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap mb-1.5">
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded uppercase tracking-wide ${PRIORITY_STYLE[r.priority] || PRIORITY_STYLE.Routine}`}>
                      {r.priority}
                    </span>
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border uppercase tracking-wide ${STATUS_STYLE[r.status] || "bg-slate-100 text-slate-600 border-slate-200"}`}>
                      {r.status}
                    </span>
                    {r.report_no && (
                      <span className="text-[10px] font-mono text-slate-400">{r.report_no}</span>
                    )}
                  </div>

                  <h3 className="text-base font-bold text-slate-800 truncate">{r.test_name}</h3>

                  <Link
                    href={`/dashboard/doctor/patients/${r.patient_id}`}
                    className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-indigo-600 transition-colors mt-0.5"
                  >
                    <User className="w-3.5 h-3.5" />
                    {r.patient_name}
                    <span className="text-slate-400">({r.patient_user_id})</span>
                  </Link>

                  {r.clinical_notes && (
                    <p className="text-xs text-slate-500 mt-1.5 line-clamp-2">{r.clinical_notes}</p>
                  )}

                  <p className="text-[11px] text-slate-400 mt-1.5 flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    Requested {r.requested_date ? new Date(r.requested_date).toLocaleString() : "—"}
                  </p>
                </div>

                <div className="flex-shrink-0">
                  {r.status === "Completed" && r.report_id ? (
                    <button
                      onClick={() => openReport(r.report_id!)}
                      disabled={busyReport === r.report_id}
                      className="flex items-center gap-2 px-4 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-sm font-bold transition-colors disabled:opacity-60"
                    >
                      {busyReport === r.report_id
                        ? <><Loader2 className="w-4 h-4 animate-spin" /> Decrypting…</>
                        : <><FileCheck className="w-4 h-4" /> View Report</>}
                    </button>
                  ) : r.status === "Completed" ? (
                    // Completed but no linked report: say so rather than
                    // showing a button that cannot do anything.
                    <span className="flex items-center gap-2 text-xs font-semibold text-amber-700 bg-amber-50 border border-amber-100 rounded-xl px-3 py-2">
                      <AlertTriangle className="w-4 h-4" /> No report filed
                    </span>
                  ) : (
                    <span className="flex items-center gap-2 text-xs font-semibold text-slate-500 bg-slate-50 border border-slate-100 rounded-xl px-3 py-2">
                      {r.status === "Pending" ? <Clock className="w-4 h-4" /> : <CheckCircle2 className="w-4 h-4" />}
                      {r.status === "Pending" ? "Awaiting laboratory" : "In the laboratory"}
                      <ChevronRight className="w-3.5 h-3.5 opacity-40" />
                    </span>
                  )}
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
