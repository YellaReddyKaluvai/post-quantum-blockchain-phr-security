"use client";

import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { FileText, CheckCircle, Upload, X } from "lucide-react";
import { getDoctorReports, getDoctorDocuments, reviewLabReport, createMedicalDocument } from "@/lib/session";

export default function ReportsAndDocuments() {
  const [activeTab, setActiveTab] = useState("reports");
  const [reports, setReports] = useState<any[]>([]);
  const [documents, setDocuments] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const [uploadModal, setUploadModal] = useState(false);
  const [docData, setDocData] = useState({ title: "", type: "", file_url: "" });

  useEffect(() => {
    async function fetchData() {
      try {
        const [rep, docs] = await Promise.all([getDoctorReports(), getDoctorDocuments()]);
        setReports(rep);
        setDocuments(docs);
      } catch (error) {
        console.error("Error fetching data:", error);
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  const handleReview = async (id: string) => {
    try {
      await reviewLabReport(id);
      setReports(reports.map(r => r.id === id ? { ...r, status: "Reviewed" } : r));
    } catch (error) {
      console.error(error);
    }
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await createMedicalDocument(docData);
      setDocuments([...documents, res]);
      setUploadModal(false);
      setDocData({ title: "", type: "", file_url: "" });
    } catch (error) {
      console.error(error);
    }
  };

  if (loading) {
    return <div className="h-64 bg-slate-200 animate-pulse rounded-2xl" />;
  }

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-6">
        <div className="flex items-center gap-3">
          <FileText className="w-6 h-6 text-cyan-600" />
          <h1 className="text-2xl font-bold text-slate-800">Reports & Documents</h1>
        </div>
        <div className="flex gap-2 bg-slate-100 p-1 rounded-xl">
          <button
            onClick={() => setActiveTab("reports")}
            className={`px-4 py-2 rounded-lg text-sm font-semibold transition-all ${
              activeTab === "reports" ? "bg-white shadow-sm text-slate-800" : "text-slate-500 hover:text-slate-700"
            }`}
          >
            Lab Reports
          </button>
          <button
            onClick={() => setActiveTab("documents")}
            className={`px-4 py-2 rounded-lg text-sm font-semibold transition-all ${
              activeTab === "documents" ? "bg-white shadow-sm text-slate-800" : "text-slate-500 hover:text-slate-700"
            }`}
          >
            Documents
          </button>
        </div>
      </div>

      {activeTab === "reports" && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {reports.length === 0 ? (
            <p className="col-span-full text-center text-slate-500 py-8 bg-white rounded-2xl border border-slate-100">No lab reports found.</p>
          ) : (
            reports.map((report, i) => (
              <motion.div key={report.id || i} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }} className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100">
                <div className="flex justify-between items-start mb-4">
                  <h3 className="font-bold text-slate-800">{report.title || "Report"}</h3>
                  <span className={`text-xs px-2 py-1 rounded-full font-bold ${report.status === "Reviewed" ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>
                    {report.status || "Pending"}
                  </span>
                </div>
                <p className="text-sm text-slate-600 mb-2">Patient: {report.patient_name}</p>
                <p className="text-xs text-slate-400 mb-6">{new Date(report.date).toLocaleDateString()}</p>
                {report.status !== "Reviewed" && (
                  <button onClick={() => handleReview(report.id)} className="w-full flex items-center justify-center gap-2 py-2 px-4 bg-cyan-50 hover:bg-cyan-100 text-cyan-700 rounded-xl font-semibold text-sm transition-colors">
                    <CheckCircle className="w-4 h-4" /> Mark as Reviewed
                  </button>
                )}
              </motion.div>
            ))
          )}
        </div>
      )}

      {activeTab === "documents" && (
        <div className="space-y-6">
          <div className="flex justify-end">
            <button onClick={() => setUploadModal(true)} className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-sm font-bold transition-colors">
              <Upload className="w-4 h-4" /> Upload Document
            </button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {documents.length === 0 ? (
              <p className="col-span-full text-center text-slate-500 py-8 bg-white rounded-2xl border border-slate-100">No documents found.</p>
            ) : (
              documents.map((doc, i) => (
                <motion.div key={doc.id || i} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }} className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100">
                  <h3 className="font-bold text-slate-800 mb-2">{doc.title}</h3>
                  <p className="text-sm text-slate-600">Type: {doc.type}</p>
                  <p className="text-xs text-slate-400 mt-4 mb-4">{new Date(doc.date).toLocaleDateString()}</p>
                  <a href={doc.file_url} target="_blank" rel="noopener noreferrer" className="block text-center w-full py-2 px-4 bg-slate-50 hover:bg-slate-100 text-slate-700 rounded-xl font-semibold text-sm transition-colors">
                    View Document
                  </a>
                </motion.div>
              ))
            )}
          </div>
        </div>
      )}

      {uploadModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-bold">Upload Document</h3>
              <button onClick={() => setUploadModal(false)}><X className="w-5 h-5 text-slate-500" /></button>
            </div>
            <form onSubmit={handleUpload}>
              <div className="space-y-4 mb-6">
                <input required type="text" placeholder="Title" className="w-full border border-slate-200 rounded-xl p-3 focus:ring-2 focus:ring-indigo-500 outline-none" value={docData.title} onChange={(e) => setDocData({ ...docData, title: e.target.value })} />
                <input required type="text" placeholder="Type (e.g. X-Ray, Scan)" className="w-full border border-slate-200 rounded-xl p-3 focus:ring-2 focus:ring-indigo-500 outline-none" value={docData.type} onChange={(e) => setDocData({ ...docData, type: e.target.value })} />
                <input required type="text" placeholder="File URL (mock)" className="w-full border border-slate-200 rounded-xl p-3 focus:ring-2 focus:ring-indigo-500 outline-none" value={docData.file_url} onChange={(e) => setDocData({ ...docData, file_url: e.target.value })} />
              </div>
              <button type="submit" className="w-full bg-indigo-600 text-white rounded-xl py-2 font-bold hover:bg-indigo-700">Upload</button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
