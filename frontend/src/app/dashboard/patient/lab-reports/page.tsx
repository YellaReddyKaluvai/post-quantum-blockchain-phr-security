"use client";

import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { TestTubes, Calendar, User, Eye, X, Activity, Download, Lock } from "lucide-react";
import { getPatientLabReports, downloadPatientLabReport } from "@/lib/session";

interface LabReportItem {
  id: string;
  name?: string;
  report_name?: string;
  type?: string;
  report_type?: string;
  status?: string;
  date?: string;
  upload_date?: string;
  uploaded_by?: string;
  uploaded_by_name?: string;
  findings?: string;
  normal_range?: string;
  [key: string]: unknown;
}

export default function LabReportsPage() {
  const [loading, setLoading] = useState(true);
  const [reports, setReports] = useState<LabReportItem[]>([]);
  const [selectedReport, setSelectedReport] = useState<LabReportItem | null>(null);
  const [isDownloading, setIsDownloading] = useState(false);

  const handleDownload = async (reportId: string, filename: string) => {
    try {
      setIsDownloading(true);
      const blob = await downloadPatientLabReport(reportId);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${filename.replace(/[^a-z0-9]/gi, '_').toLowerCase()}.json`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (error) {
      console.error("Download failed:", error);
      alert("Failed to securely download and decrypt the report. Please check your keys.");
    } finally {
      setIsDownloading(false);
    }
  };


  useEffect(() => {
    async function loadData() {
      try {
        const data = await getPatientLabReports();
        setReports(data);
      } catch (error) {
        console.error("Failed to load lab reports:", error);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  const getTypeColor = (type: string) => {
    const t = type.toLowerCase();
    if (t.includes("cbc") || t.includes("blood")) return "bg-blue-100 text-blue-700";
    if (t.includes("sugar") || t.includes("glucose")) return "bg-amber-100 text-amber-700";
    if (t.includes("lipid") || t.includes("cholesterol")) return "bg-purple-100 text-purple-700";
    if (t.includes("urine")) return "bg-yellow-100 text-yellow-700";
    return "bg-slate-100 text-slate-700";
  };

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case "pending": return "bg-amber-50 text-amber-600 border-amber-200";
      case "completed": return "bg-emerald-50 text-emerald-600 border-emerald-200";
      case "reviewed": return "bg-cyan-50 text-cyan-600 border-cyan-200";
      default: return "bg-slate-50 text-slate-600 border-slate-200";
    }
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="h-8 w-48 bg-slate-200 animate-pulse rounded-md"></div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3].map((i) => (
            <div key={i} className="bg-white rounded-2xl p-6 h-48 animate-pulse shadow-sm border border-slate-100"></div>
          ))}
        </div>
      </div>
    );
  }

  const containerVariants = {
    hidden: { opacity: 0 },
    show: {
      opacity: 1,
      transition: { staggerChildren: 0.1 }
    }
  };

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-xl md:text-2xl font-bold text-slate-800">Lab Reports</h1>
        <p className="text-slate-500 mt-1">View and manage your laboratory test results.</p>
      </motion.div>

      {reports.length === 0 ? (
        <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-12 text-center">
          <TestTubes className="w-16 h-16 text-slate-200 mx-auto mb-4" />
          <h3 className="text-lg font-bold text-slate-700">No Lab Reports Found</h3>
          <p className="text-slate-500">Your laboratory results will appear here once uploaded.</p>
        </div>
      ) : (
        <motion.div
          variants={containerVariants}
          initial="hidden"
          animate="show"
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6"
        >
          {reports.map((report: LabReportItem) => (
            <motion.div
              key={report.id}
              variants={{ hidden: { opacity: 0, y: 20 }, show: { opacity: 1, y: 0 } }}
              className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden hover:shadow-lg transition-shadow flex flex-col"
            >
              <div className="p-5 border-b border-slate-100 flex-1">
                <div className="flex justify-between items-start mb-4">
                  <span className={`px-2.5 py-1 rounded-md text-xs font-bold ${getTypeColor(report.report_type || report.type || "Other")}`}>
                    {report.report_type || report.type || "Other"}
                  </span>
                  <span className={`px-2.5 py-1 rounded-full text-xs font-semibold border ${getStatusColor(report.status || "Pending")}`}>

                    {report.status}
                  </span>
                </div>
                <h3 className="text-lg font-bold text-slate-800 line-clamp-2 mb-2">{report.name}</h3>
                
                <div className="space-y-2 mt-4 text-sm text-slate-500">
                  <div className="flex items-center gap-2">
                    <Calendar className="w-4 h-4 text-slate-400" />
                    <span>{new Date(report.upload_date || Date.now()).toLocaleDateString()}</span>

                  </div>
                  <div className="flex items-center gap-2">
                    <User className="w-4 h-4 text-slate-400" />
                    <span>Uploaded by: {report.uploaded_by}</span>
                  </div>
                </div>
              </div>
              <div className="bg-slate-50 p-4">
                <button
                  onClick={() => setSelectedReport(report)}
                  className="w-full flex items-center justify-center gap-2 py-2 bg-white border border-slate-200 rounded-xl text-sm font-semibold text-slate-700 hover:bg-slate-100 hover:text-slate-900 transition-colors shadow-sm"
                >
                  <Eye className="w-4 h-4" /> View Details
                </button>
              </div>
            </motion.div>
          ))}
        </motion.div>
      )}

      {/* Modal Overlay for Report Details */}
      <AnimatePresence>
        {selectedReport && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setSelectedReport(null)}
              className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-40"
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              className="fixed inset-0 m-auto w-full max-w-2xl h-fit max-h-[85vh] bg-white rounded-3xl shadow-2xl z-50 overflow-hidden flex flex-col"
            >
              <div className="p-6 border-b border-slate-100 flex items-center justify-between bg-slate-50">
                <div className="flex items-center gap-3">
                  <div className="p-2.5 bg-emerald-100 text-emerald-600 rounded-xl">
                    <Activity className="w-6 h-6" />
                  </div>
                  <div>
                    <h2 className="text-xl font-bold text-slate-800">{selectedReport.name}</h2>
                    <p className="text-sm text-slate-500">{new Date(selectedReport.upload_date || Date.now()).toLocaleDateString()} • {selectedReport.report_type || selectedReport.type}</p>

                  </div>
                </div>
                <button
                  onClick={() => setSelectedReport(null)}
                  className="p-2 rounded-full hover:bg-slate-200 text-slate-500 transition-colors"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
              
              <div className="p-6 overflow-y-auto custom-scrollbar">
                {selectedReport.findings ? (
                  <div className="space-y-6">
                    <div>
                      <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wider mb-3">Key Findings</h3>
                      <div className="bg-slate-50 rounded-xl p-4 border border-slate-100">
                        <p className="text-slate-700 whitespace-pre-wrap">{selectedReport.findings}</p>
                      </div>
                    </div>
                    
                    {selectedReport.normal_range && (
                      <div>
                        <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wider mb-3">Reference / Normal Range</h3>
                        <div className="bg-emerald-50 rounded-xl p-4 border border-emerald-100">
                          <p className="text-emerald-800 whitespace-pre-wrap">{selectedReport.normal_range}</p>
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-center py-12">
                    <TestTubes className="w-12 h-12 text-slate-200 mx-auto mb-3" />
                    <p className="text-slate-500">Detailed findings are not available for this report.</p>
                  </div>
                )}
                
                {/* Secure Download Button */}
                <div className="mt-8">
                  <button
                    onClick={() => handleDownload(selectedReport.id, selectedReport.name || selectedReport.report_name || "report")}
                    disabled={isDownloading}
                    className="w-full flex items-center justify-center gap-3 py-4 bg-slate-900 text-white rounded-2xl font-bold hover:bg-slate-800 transition-colors disabled:bg-slate-300 disabled:cursor-not-allowed"
                  >
                    {isDownloading ? (
                      <>
                        <Lock className="w-5 h-5 animate-pulse text-emerald-400" />
                        Decapsulating & Decrypting File...
                      </>
                    ) : (
                      <>
                        <Download className="w-5 h-5" />
                        Download Original File (PQC Secured)
                      </>
                    )}
                  </button>
                  <p className="text-center text-xs text-slate-500 mt-3 flex items-center justify-center gap-1">
                    <Lock className="w-3 h-3" /> End-to-end encrypted via AWS S3 & ML-KEM
                  </p>
                </div>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
