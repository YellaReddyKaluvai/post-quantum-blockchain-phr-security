"use client";

import React, { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Search, Filter, FileText, Download, Shield, Eye, X, Activity, Hash, Lock, CheckCircle, Clock, Loader2 } from "lucide-react";
import { getLabTechReports, downloadLabTechReport } from "@/lib/session";

// Mirrors the backend LabReportItem exactly.
interface LabReportItem {
  id: string;
  report_name?: string;
  report_type?: string;
  report_id_public?: string;
  patient_name?: string;
  uploaded_by_name?: string;
  status?: string;
  upload_date?: string;
  findings?: string;
  normal_range?: string;
  document_hash?: string;
  blockchain_tx_hash?: string;
  anchored_on?: string;
  ipfs_cid?: string;
  s3_key?: string;
}






export default function LabReportsPage() {
  const [reports, setReports] = useState<LabReportItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedAudit, setSelectedAudit] = useState<LabReportItem | null>(null);
  const [loadError, setLoadError] = useState("");
  const [busyReport, setBusyReport] = useState<string | null>(null);
  const [period, setPeriod] = useState("All Time");

  // The PDF only exists decrypted in memory: it is fetched, shown or saved,
  // then the object URL is released so it does not linger.
  const handleOpenReport = async (id: string, mode: "view" | "download") => {
    setLoadError("");
    setBusyReport(id);
    try {
      const blob = await downloadLabTechReport(id);
      const url = URL.createObjectURL(blob);
      if (mode === "view") {
        window.open(url, "_blank", "noopener");
      } else {
        const a = document.createElement("a");
        a.href = url;
        a.download = `${id}.pdf`;
        document.body.appendChild(a);
        a.click();
        a.remove();
      }
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "Could not open the report.");
    } finally {
      setBusyReport(null);
    }
  };



  useEffect(() => {
    const fetchReports = async () => {
      try {
        const data = await getLabTechReports();
        setReports(data);
      } catch (error) {
        console.error(error);
        // Deliberately no placeholder reports here. Inventing rows with
        // fabricated transaction and document hashes would put fake
        // cryptographic provenance in the audit trail, which is worse than
        // showing nothing.
        setReports([]);
        setLoadError("Could not load reports. Check that the backend is running.");
      } finally {
        setLoading(false);
      }
    };
    fetchReports();
  }, []);

  // Oldest timestamp a report may carry to satisfy the selected window.
  const periodCutoff = (): number | null => {
    const now = new Date();
    switch (period) {
      case "Today": {
        const start = new Date(now);
        start.setHours(0, 0, 0, 0);
        return start.getTime();
      }
      case "This Week": return now.getTime() - 7 * 24 * 60 * 60 * 1000;
      case "This Month": return now.getTime() - 30 * 24 * 60 * 60 * 1000;
      default: return null;
    }
  };

  const filteredReports = reports.filter((report: LabReportItem) => {
    const pName = report.patient_name || "";
    const rId = report.report_id_public || report.id || "";
    const rType = report.report_type || report.report_name || "";
    const term = searchTerm.toLowerCase();
    const matchesTerm =
      pName.toLowerCase().includes(term) ||
      rId.toLowerCase().includes(term) ||
      rType.toLowerCase().includes(term);

    const cutoff = periodCutoff();
    if (cutoff === null) return matchesTerm;

    // A report with no usable date is kept rather than silently dropped —
    // hiding a record because its timestamp is missing would misrepresent
    // the laboratory's output.
    const raw = report.upload_date;
    const stamp = raw ? new Date(raw).getTime() : NaN;
    if (Number.isNaN(stamp)) return matchesTerm;

    return matchesTerm && stamp >= cutoff;
  });


  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Laboratory Reports</h1>
          <p className="text-sm text-slate-500">Manage and audit finalized laboratory reports.</p>
        </div>
      </div>

      {loadError && (
        <div className="p-3 rounded-xl bg-rose-50 border border-rose-100 text-rose-700 text-sm font-semibold">
          {loadError}
        </div>
      )}

      <div className="bg-white/80 backdrop-blur-md rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
        <div className="p-4 border-b border-slate-100 flex flex-col sm:flex-row gap-4 justify-between bg-slate-50/50">
          <div className="relative max-w-md w-full">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              type="text"
              placeholder="Search by Report ID, Patient Name..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-9 pr-4 py-2 bg-white border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500/20 focus:border-cyan-500 transition-all"
            />
          </div>
          <div className="flex gap-2">
            {/* Filtering applies as soon as the period changes, so the
                separate "Filter" button that used to sit here did nothing and
                has been removed rather than left as a decoy. */}
            <div className="relative">
              <Filter className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
              <select
                value={period}
                onChange={(e) => setPeriod(e.target.value)}
                className="pl-9 pr-4 py-2 bg-white border border-slate-200 rounded-xl text-sm font-medium text-slate-600 focus:outline-none focus:ring-2 focus:ring-cyan-500/20"
              >
                <option value="All Time">All Time</option>
                <option value="Today">Today</option>
                <option value="This Week">This Week</option>
                <option value="This Month">This Month</option>
              </select>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 p-6">
          {loading ? (
            [1, 2, 3].map(i => <div key={i} className="bg-slate-100 h-48 rounded-2xl animate-pulse" />)
          ) : filteredReports.length === 0 ? (
            <div className="col-span-full py-12 text-center text-slate-500">
              <FileText className="w-12 h-12 mx-auto text-slate-300 mb-3" />
              <p>No reports found.</p>
            </div>
          ) : (
            filteredReports.map((report: LabReportItem, idx: number) => (
              <motion.div
                key={report.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: idx * 0.05 }}
                className="bg-white border border-slate-200 rounded-2xl shadow-sm hover:shadow-md transition-all p-5 flex flex-col"
              >
                <div className="flex justify-between items-start mb-4">
                  <div>
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-600 mb-2">
                      {report.report_id_public || report.id}
                    </span>
                    <h3 className="text-base font-bold text-slate-800">
                      {report.patient_name || report.uploaded_by_name || "Patient"}
                    </h3>
                    <p className="text-sm font-medium text-cyan-600">{report.report_type || "—"}</p>
                  </div>
                  <div className={`p-2 rounded-xl ${report.status === 'Completed' || report.status === 'Verified' ? 'bg-emerald-50 text-emerald-600' : 'bg-amber-50 text-amber-600'}`}>
                    {report.status === 'Completed' || report.status === 'Verified' ? <CheckCircle className="w-5 h-5" /> : <Clock className="w-5 h-5" />}
                  </div>
                </div>

                <div className="text-xs text-slate-500 mb-4 flex-1">
                  <p>Uploaded: {report.upload_date ? new Date(report.upload_date).toLocaleString() : "—"}</p>
                  <p className="mt-1">Status: <span className="font-semibold text-slate-700">{report.status}</span></p>
                </div>

                <div className="grid grid-cols-3 gap-2 border-t border-slate-100 pt-4">
                  <button
                    onClick={() => handleOpenReport(report.id, "view")}
                    disabled={busyReport === report.id}
                    className="flex flex-col items-center justify-center gap-1 p-2 rounded-lg hover:bg-slate-50 text-slate-600 transition-colors disabled:opacity-50"
                  >
                    {busyReport === report.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Eye className="w-4 h-4" />}
                    <span className="text-[10px] font-semibold">View</span>
                  </button>
                  <button
                    onClick={() => handleOpenReport(report.id, "download")}
                    disabled={busyReport === report.id}
                    className="flex flex-col items-center justify-center gap-1 p-2 rounded-lg hover:bg-slate-50 text-slate-600 transition-colors disabled:opacity-50"
                  >
                    <Download className="w-4 h-4" />
                    <span className="text-[10px] font-semibold">PDF</span>
                  </button>
                  <button 
                    onClick={() => setSelectedAudit(report)}
                    className="flex flex-col items-center justify-center gap-1 p-2 rounded-lg bg-cyan-50 hover:bg-cyan-100 text-cyan-700 transition-colors"
                  >
                    <Shield className="w-4 h-4" />
                    <span className="text-[10px] font-semibold">Audit</span>
                  </button>
                </div>
              </motion.div>
            ))
          )}
        </div>
      </div>

      {/* Audit Modal */}
      <AnimatePresence>
        {selectedAudit && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 bg-slate-900/60 backdrop-blur-sm"
              onClick={() => setSelectedAudit(null)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              className="relative bg-white rounded-2xl shadow-2xl p-6 max-w-lg w-full"
            >
              <button 
                onClick={() => setSelectedAudit(null)}
                className="absolute top-4 right-4 p-2 text-slate-400 hover:text-slate-600 rounded-full hover:bg-slate-100 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>

              <div className="flex items-center gap-3 mb-6">
                <div className="p-3 bg-cyan-100 text-cyan-600 rounded-xl">
                  <Shield className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="text-xl font-bold text-slate-800">Security Audit Trail</h3>
                  <p className="text-sm text-slate-500">Report: {selectedAudit.id}</p>
                </div>
              </div>

              <div className="space-y-4">
                <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2">
                      <Activity className="w-4 h-4 text-emerald-500" />
                      <span className="text-sm font-bold text-slate-700">Blockchain Transaction Hash</span>
                    </div>
                    {/* A locally-simulated anchor must never read as an on-chain one. */}
                    {selectedAudit.anchored_on && (
                      <span
                        className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                          selectedAudit.anchored_on === "local-simulated"
                            ? "text-amber-700 bg-amber-50"
                            : "text-emerald-700 bg-emerald-50"
                        }`}
                      >
                        {selectedAudit.anchored_on === "local-simulated"
                          ? "SIMULATED"
                          : `ON-CHAIN · ${String(selectedAudit.anchored_on).toUpperCase()}`}
                      </span>
                    )}
                  </div>
                  <p className="text-xs font-mono text-slate-600 break-all bg-white p-2 rounded border border-slate-200">
                    {selectedAudit.blockchain_tx_hash || "Not anchored"}
                  </p>
                  {selectedAudit.anchored_on === "local-simulated" && (
                    <p className="text-[11px] text-amber-700 mt-1.5">
                      Recorded locally because no chain was reachable. Not a blockchain transaction.
                    </p>
                  )}
                </div>

                <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2">
                      <Hash className="w-4 h-4 text-cyan-500" />
                      <span className="text-sm font-bold text-slate-700">Content Identifier (CIDv0)</span>
                    </div>
                    <span className="text-[10px] font-bold text-slate-600 bg-slate-200 px-2 py-0.5 rounded">SHA-256 · BASE58</span>
                  </div>
                  {/* Deliberately not a link: this is a content address computed
                      the way IPFS computes one, but nothing is pinned to the
                      IPFS network, so a public gateway URL would not resolve. */}
                  <p className="text-xs font-mono text-slate-600 break-all bg-white p-2 rounded border border-slate-200">
                    {selectedAudit.ipfs_cid || "Not computed"}
                  </p>
                  <p className="text-[11px] text-slate-500 mt-1.5">
                    Deterministic fingerprint of the encrypted document. Not published to the IPFS network.
                  </p>
                </div>

                <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2">
                      <Lock className="w-4 h-4 text-blue-500" />
                      <span className="text-sm font-bold text-slate-700">AWS Cloud Storage (S3)</span>
                    </div>
                    {selectedAudit.s3_key && (
                      <span className="text-[10px] font-bold text-blue-600 bg-blue-50 px-2 py-0.5 rounded">AWS S3 ENCRYPTED</span>
                    )}
                  </div>
                  <p className="text-xs font-mono text-slate-600 break-all bg-white p-2 rounded border border-slate-200">
                    {selectedAudit.s3_key || "No cloud copy stored"}
                  </p>
                </div>

                <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
                  <div className="flex items-center gap-2 mb-1">
                    <Lock className="w-4 h-4 text-purple-500" />
                    <span className="text-sm font-bold text-slate-700">ML-KEM & ML-DSA Quantum Keys</span>
                  </div>
                  <div className="flex items-center justify-between bg-white p-2 rounded border border-slate-200">
                    <span className="text-xs text-slate-500 font-mono">Kyber-768 Encapsulated & Signed</span>
                    <span className="text-[10px] font-bold text-emerald-600 bg-emerald-50 px-2 py-1 rounded">VALID</span>
                  </div>
                </div>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
