"use client";

import React, { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Film, ZoomIn, Download, X, Activity, FileCheck, Lock, Loader2 } from "lucide-react";
import { getImagingReports, getImagingImage } from "@/lib/session";

interface ImagingReportItem {
  id: string;
  title?: string;
  report_name?: string;
  scan_type?: string;
  type?: string;
  date?: string;
  upload_date?: string;
  created_at?: string;
  patient_name?: string;
  patientName?: string;
  patient_user_id?: string;
  patientId?: string;
  image_url?: string;
  imageUrl?: string;
  // The payload itself is never in the list response; this only says whether
  // an encrypted image exists to decrypt.
  has_image?: boolean;
  document_hash?: string;
  kem_algorithm?: string;
  signature_algorithm?: string;
  blockchain_tx_hash?: string;
  file_url?: string;
  findings?: string;
  exam_type?: string;
  examType?: string;
  scan_region?: string;
  scanRegion?: string;
  clinical_history?: string;
  history?: string;
  impression?: string;
  linkedReport?: string | null;

  [key: string]: unknown;
}








export default function ImagingReportsPage() {
  const [reports, setReports] = useState<ImagingReportItem[]>([]);

  const [loading, setLoading] = useState(true);
  const [selectedImage, setSelectedImage] = useState<string | null>(null);
  // Decrypted images, keyed by study id. Populated only when a study is opened.
  const [decrypted, setDecrypted] = useState<Record<string, string>>({});
  const [decrypting, setDecrypting] = useState<string | null>(null);
  const [decryptError, setDecryptError] = useState<string | null>(null);

  const handleViewImage = async (id: string) => {
    setDecryptError(null);
    if (decrypted[id]) {
      setSelectedImage(decrypted[id]);
      return;
    }
    setDecrypting(id);
    try {
      const { image_data } = await getImagingImage(id);
      setDecrypted((prev) => ({ ...prev, [id]: image_data }));
      setSelectedImage(image_data);
    } catch (err) {
      setDecryptError(err instanceof Error ? err.message : "Failed to decrypt image");
    } finally {
      setDecrypting(null);
    }
  };

  useEffect(() => {
    const fetchReports = async () => {
      try {
        const data = await getImagingReports();
        setReports(data);
      } catch (error) {
        console.error(error);
        setReports([
          {
            id: "IMG-001",
            patientName: "Jane Smith",
            patientId: "PAT-9932",
            scanRegion: "Brain",
            examType: "MRI without Contrast",
            history: "Persistent headaches, dizzy spells.",
            findings: "No acute intracranial hemorrhage or mass effect. Ventricular system is unremarkable.",
            impression: "Normal MRI Brain.",
            date: "2026-07-24",
            imageUrl: "https://images.unsplash.com/photo-1559757175-5700dde675bc?w=800&auto=format&fit=crop&q=60",
            linkedReport: "REP-9922"
          },
          {
            id: "IMG-002",
            patientName: "Mark Johnson",
            patientId: "PAT-1123",
            scanRegion: "Chest",
            examType: "X-Ray PA View",
            history: "Cough for 2 weeks, mild fever.",
            findings: "Clear lung fields. No pleural effusion or pneumothorax.",
            impression: "Normal Chest X-Ray.",
            date: "2026-07-25",
            imageUrl: "https://images.unsplash.com/photo-1516069675273-df2676b10702?w=800&auto=format&fit=crop&q=60",
            linkedReport: null
          }
        ]);
      } finally {
        setLoading(false);
      }
    };
    fetchReports();
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Imaging Reports</h1>
          <p className="text-sm text-slate-500">Scans are encrypted at rest and decrypted only when opened.</p>
        </div>
      </div>

      {decryptError && (
        <div className="p-3 rounded-xl bg-rose-50 border border-rose-100 text-rose-700 text-sm font-semibold">
          {decryptError}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {loading ? (
          [1, 2].map(i => <div key={i} className="bg-white h-96 rounded-2xl shadow-sm border border-slate-200 animate-pulse" />)
        ) : reports.length === 0 ? (
          <div className="col-span-full py-12 text-center bg-white rounded-2xl shadow-sm border border-slate-200 text-slate-500">
            <Film className="w-12 h-12 mx-auto text-slate-300 mb-3" />
            <p>No imaging reports found.</p>
          </div>
        ) : (
          reports.map((report: ImagingReportItem, idx: number) => (

            <motion.div
              key={report.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.1 }}
              className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden flex flex-col"
            >
              <div className="flex border-b border-slate-100">
                <div className="w-1/3 relative bg-slate-900 overflow-hidden flex items-center justify-center min-h-[200px]">
                  {decrypted[report.id] ? (
                    <>
                      <img src={decrypted[report.id]} alt="Scan" className="w-full h-full object-cover opacity-80 mix-blend-screen" />
                      <button
                        onClick={() => setSelectedImage(decrypted[report.id])}
                        className="absolute inset-0 bg-black/40 flex flex-col items-center justify-center opacity-0 hover:opacity-100 transition-opacity"
                      >
                        <ZoomIn className="w-8 h-8 text-white mb-2" />
                        <span className="text-xs text-white font-bold">View Full</span>
                      </button>
                    </>
                  ) : report.has_image ? (
                    // Encrypted at rest: decrypted only on explicit request.
                    <button
                      onClick={() => handleViewImage(report.id)}
                      disabled={decrypting === report.id}
                      className="absolute inset-0 flex flex-col items-center justify-center text-slate-400 hover:text-cyan-300 transition-colors disabled:opacity-60"
                    >
                      {decrypting === report.id ? (
                        <>
                          <Loader2 className="w-8 h-8 mb-2 animate-spin" />
                          <span className="text-[11px] font-bold">Decrypting…</span>
                        </>
                      ) : (
                        <>
                          <Lock className="w-8 h-8 mb-2" />
                          <span className="text-[11px] font-bold">Encrypted</span>
                          <span className="text-[10px] mt-1 underline">Decrypt &amp; view</span>
                        </>
                      )}
                    </button>
                  ) : (
                    <Film className="w-12 h-12 text-slate-700" />
                  )}
                </div>
                <div className="w-2/3 p-4 bg-slate-50">
                  <div className="flex justify-between items-start mb-2">
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-cyan-100 text-cyan-700">
                      {report.id}
                    </span>
                    <span className="text-xs font-semibold text-slate-500">
                      {report.created_at ? new Date(report.created_at).toLocaleDateString() : report.date}
                    </span>
                  </div>
                  <h3 className="text-base font-bold text-slate-800">
                    {report.patient_name || report.patientName || "Patient"}{" "}
                    <span className="text-xs font-normal text-slate-500">
                      ({report.patient_user_id || report.patientId || ""})
                    </span>
                  </h3>
                  <p className="text-sm font-medium text-cyan-600 mt-1">{report.exam_type || report.examType}</p>
                  <div className="mt-3 flex items-center gap-2 text-xs text-slate-600">
                    <Activity className="w-4 h-4 text-slate-400" />
                    <span>Region: <span className="font-semibold">{report.scan_region || report.scanRegion}</span></span>
                  </div>
                </div>
              </div>

              <div className="p-4 space-y-3 flex-1">
                <div>
                  <h4 className="text-xs font-bold text-slate-700 mb-1">Clinical History</h4>
                  <p className="text-sm text-slate-600">{report.clinical_history || report.history}</p>
                </div>
                <div>
                  <h4 className="text-xs font-bold text-slate-700 mb-1">Findings</h4>
                  <p className="text-sm text-slate-600">{report.findings}</p>
                </div>
                <div>
                  <h4 className="text-xs font-bold text-slate-700 mb-1">Impression</h4>
                  <p className="text-sm font-semibold text-slate-800">{report.impression}</p>
                </div>
              </div>

              <div className="p-4 border-t border-slate-100 bg-slate-50/50 flex justify-between items-center">
                {report.linkedReport ? (
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-emerald-600 bg-emerald-50 px-2 py-1 rounded border border-emerald-100">
                    <FileCheck className="w-4 h-4" />
                    Linked: {report.linkedReport}
                  </div>
                ) : (
                  <div className="text-xs text-slate-500 italic">No linked report</div>
                )}
                
                <div className="flex gap-2">
                  <button className="p-2 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600 transition-colors tooltip" title="Download Image">
                    <Download className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </motion.div>
          ))
        )}
      </div>

      {/* Image Zoom Modal */}
      <AnimatePresence>
        {selectedImage && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 bg-slate-900/90 backdrop-blur-md"
              onClick={() => setSelectedImage(null)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="relative max-w-5xl w-full"
            >
              <button 
                onClick={() => setSelectedImage(null)}
                className="absolute -top-12 right-0 p-2 text-white hover:text-slate-300 transition-colors"
              >
                <X className="w-8 h-8" />
              </button>
              <img src={selectedImage} alt="Full Scan" className="w-full h-auto rounded-lg shadow-2xl" />
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
