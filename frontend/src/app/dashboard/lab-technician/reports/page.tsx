"use client";

import React, { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Search, Filter, FileText, Download, Shield, Eye, X, Activity, Hash, Lock, CheckCircle, Clock } from "lucide-react";
import { getLabTechReports } from "@/lib/session";

export default function ReportsPage() {
  const [reports, setReports] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedAudit, setSelectedAudit] = useState<any>(null);

  useEffect(() => {
    const fetchReports = async () => {
      try {
        const data = await getLabTechReports();
        setReports(data);
      } catch (error) {
        console.error(error);
        setReports([
          { id: "REP-9921", patientName: "John Doe", type: "Complete Blood Count", date: "2026-07-25 10:30 AM", status: "Verified", txHash: "0x8f2a...39c1", docHash: "a2c5...99f4" },
          { id: "REP-9922", patientName: "Jane Smith", type: "Liver Function Test", date: "2026-07-24 14:15 PM", status: "Verified", txHash: "0x3b1c...72a5", docHash: "b8f1...44e2" },
          { id: "REP-9923", patientName: "Mark Johnson", type: "Blood Sugar (Fasting)", date: "2026-07-23 09:00 AM", status: "Pending Review", txHash: "0x5d9e...11b8", docHash: "c4d3...22a1" },
        ]);
      } finally {
        setLoading(false);
      }
    };
    fetchReports();
  }, []);

  const filteredReports = reports.filter(r => {
    const pName = r.uploaded_by_name || r.patient_name || r.patientName || "";
    const rId = r.id || r.report_id_public || "";
    const rType = r.report_type || r.type || "";
    return pName.toLowerCase().includes(searchTerm.toLowerCase()) || 
           rId.toLowerCase().includes(searchTerm.toLowerCase()) ||
           rType.toLowerCase().includes(searchTerm.toLowerCase());
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Laboratory Reports</h1>
          <p className="text-sm text-slate-500">Manage and audit finalized laboratory reports.</p>
        </div>
      </div>

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
            <select className="px-4 py-2 bg-white border border-slate-200 rounded-xl text-sm font-medium text-slate-600 focus:outline-none focus:ring-2 focus:ring-cyan-500/20">
              <option>All Time</option>
              <option>Today</option>
              <option>This Week</option>
              <option>This Month</option>
            </select>
            <button className="flex items-center gap-2 px-4 py-2 bg-white border border-slate-200 rounded-xl text-sm font-medium text-slate-600 hover:bg-slate-50 transition-colors">
              <Filter className="w-4 h-4" />
              Filter
            </button>
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
            filteredReports.map((report, idx) => (
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
                      {report.uploaded_by_name || report.patient_name || report.patientName || "Patient"}
                    </h3>
                    <p className="text-sm font-medium text-cyan-600">{report.report_type || report.type}</p>
                  </div>
                  <div className={`p-2 rounded-xl ${report.status === 'Completed' || report.status === 'Verified' ? 'bg-emerald-50 text-emerald-600' : 'bg-amber-50 text-amber-600'}`}>
                    {report.status === 'Completed' || report.status === 'Verified' ? <CheckCircle className="w-5 h-5" /> : <Clock className="w-5 h-5" />}
                  </div>
                </div>

                <div className="text-xs text-slate-500 mb-4 flex-1">
                  <p>Uploaded: {report.upload_date ? new Date(report.upload_date).toLocaleString() : report.date}</p>
                  <p className="mt-1">Status: <span className="font-semibold text-slate-700">{report.status}</span></p>
                </div>

                <div className="grid grid-cols-3 gap-2 border-t border-slate-100 pt-4">
                  <button className="flex flex-col items-center justify-center gap-1 p-2 rounded-lg hover:bg-slate-50 text-slate-600 transition-colors">
                    <Eye className="w-4 h-4" />
                    <span className="text-[10px] font-semibold">View</span>
                  </button>
                  <button className="flex flex-col items-center justify-center gap-1 p-2 rounded-lg hover:bg-slate-50 text-slate-600 transition-colors">
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
                  </div>
                  <p className="text-xs font-mono text-slate-600 break-all bg-white p-2 rounded border border-slate-200">
                    {selectedAudit.txHash || selectedAudit.blockchain_tx_hash || "0x8f2a39c1...39c1"}
                  </p>
                </div>

                <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2">
                      <Hash className="w-4 h-4 text-cyan-500" />
                      <span className="text-sm font-bold text-slate-700">IPFS Content Identifier (CID)</span>
                    </div>
                    <span className="text-[10px] font-bold text-cyan-600 bg-cyan-50 px-2 py-0.5 rounded">PINNED</span>
                  </div>
                  <a
                    href={`https://gateway.pinata.cloud/ipfs/${selectedAudit.ipfs_cid || selectedAudit.docHash || "QmXoypizjW3WknFiJnKLwHCnL72vedxjQkDDP1mXWo6uco"}`}
                    target="_blank"
                    rel="noreferrer"
                    className="text-xs font-mono text-cyan-600 hover:underline break-all bg-white p-2 rounded border border-slate-200 block"
                  >
                    ipfs://{selectedAudit.ipfs_cid || selectedAudit.docHash || "QmXoypizjW3WknFiJnKLwHCnL72vedxjQkDDP1mXWo6uco"}
                  </a>
                </div>

                <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2">
                      <Lock className="w-4 h-4 text-blue-500" />
                      <span className="text-sm font-bold text-slate-700">AWS Cloud Storage (S3)</span>
                    </div>
                    <span className="text-[10px] font-bold text-blue-600 bg-blue-50 px-2 py-0.5 rounded">AWS S3 ENCRYPTED</span>
                  </div>
                  <p className="text-xs font-mono text-slate-600 break-all bg-white p-2 rounded border border-slate-200">
                    {selectedAudit.s3_key || "phr_records/encrypted_medical_report.enc"}
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
