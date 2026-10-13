"use client";

import React, { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Film, ZoomIn, Download, X, Activity, FileCheck, Lock, Loader2, Plus, Upload } from "lucide-react";
import { getImagingReports, getImagingImage, uploadImagingReport, searchPatientsForLab } from "@/lib/session";
import PatientSearchSelect from "@/components/PatientSearchSelect";

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

}









interface SelectedPatient {
  id: string;
  user_id: string;
  full_name: string;
  email: string;
  gender: string;
}

const EXAM_TYPES = ["X-Ray", "MRI", "CT Scan", "Ultrasound", "Mammography", "PET Scan"];

function UploadImagingModal({ onClose, onUploaded }: { onClose: () => void; onUploaded: () => void }) {
  const [patient, setPatient] = useState<SelectedPatient | null>(null);
  const [form, setForm] = useState({
    scan_region: "", exam_type: "X-Ray", clinical_history: "",
    findings: "", impression: "", recommendations: "",
  });
  const [imageData, setImageData] = useState("");
  const [fileName, setFileName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  // Read the scan into a data URI. The file never leaves the browser
  // unencrypted: the server AES-encrypts it before anything is stored.
  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 4 * 1024 * 1024) {
      setError("Image must be 4 MB or smaller.");
      return;
    }
    setError("");
    setFileName(file.name);
    const reader = new FileReader();
    reader.onload = () => setImageData(String(reader.result));
    reader.onerror = () => setError("Could not read that file.");
    reader.readAsDataURL(file);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (!patient) { setError("Select a patient."); return; }
    if (!imageData) { setError("Attach the scan image."); return; }
    if (!form.scan_region.trim()) { setError("Enter the scan region."); return; }
    setSubmitting(true);
    try {
      await uploadImagingReport({
        patient_id: patient.id,
        scan_region: form.scan_region,
        exam_type: form.exam_type,
        clinical_history: form.clinical_history || undefined,
        findings: form.findings || undefined,
        impression: form.impression || undefined,
        recommendations: form.recommendations || undefined,
        image_data: imageData,
      });
      onUploaded();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setSubmitting(false);
    }
  };

  const inputClass = "w-full border border-slate-200 rounded-xl p-2.5 text-sm focus:ring-2 focus:ring-cyan-500 outline-none";
  const labelClass = "block text-xs font-bold text-slate-500 mb-1 uppercase tracking-wide";

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg p-6 max-h-[90vh] overflow-y-auto">
        <div className="flex justify-between items-center mb-1">
          <h3 className="text-lg font-bold">Upload Imaging Study</h3>
          <button onClick={onClose}><X className="w-5 h-5 text-slate-500" /></button>
        </div>
        <p className="text-xs text-slate-500 mb-4">
          The scan is encrypted before storage — only ciphertext reaches the cloud.
        </p>

        {error && <div className="p-3 mb-4 rounded-xl bg-rose-50 border border-rose-100 text-rose-600 text-xs font-semibold">{error}</div>}

        <form onSubmit={handleSubmit} className="space-y-3">
          <PatientSearchSelect
            onSelect={(p) => setPatient(p as SelectedPatient)}
            searchFn={searchPatientsForLab}
            selectedPatient={patient}
            onClear={() => setPatient(null)}
            label="Patient *"
          />

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelClass}>Exam Type *</label>
              <select className={inputClass} value={form.exam_type}
                onChange={(e) => setForm({ ...form, exam_type: e.target.value })}>
                {EXAM_TYPES.map((x) => <option key={x} value={x}>{x}</option>)}
              </select>
            </div>
            <div>
              <label className={labelClass}>Scan Region *</label>
              <input type="text" required className={inputClass} placeholder="e.g. Chest"
                value={form.scan_region}
                onChange={(e) => setForm({ ...form, scan_region: e.target.value })} />
            </div>
          </div>

          <div>
            <label className={labelClass}>Scan Image *</label>
            <label className="flex items-center gap-2 border border-dashed border-slate-300 rounded-xl p-3 cursor-pointer hover:bg-slate-50 transition-colors">
              <Upload className="w-4 h-4 text-slate-400 flex-shrink-0" />
              <span className="text-sm text-slate-600 truncate">{fileName || "Choose an image (max 4 MB)"}</span>
              <input type="file" accept="image/*" className="hidden" onChange={handleFile} />
            </label>
          </div>

          <div>
            <label className={labelClass}>Clinical History</label>
            <textarea className={inputClass} rows={2} placeholder="Reason for the examination"
              value={form.clinical_history}
              onChange={(e) => setForm({ ...form, clinical_history: e.target.value })} />
          </div>
          <div>
            <label className={labelClass}>Findings</label>
            <textarea className={inputClass} rows={3} placeholder="Systematic description of the findings"
              value={form.findings}
              onChange={(e) => setForm({ ...form, findings: e.target.value })} />
          </div>
          <div>
            <label className={labelClass}>Impression</label>
            <textarea className={inputClass} rows={2} placeholder="Summary conclusion"
              value={form.impression}
              onChange={(e) => setForm({ ...form, impression: e.target.value })} />
          </div>
          <div>
            <label className={labelClass}>Recommendations</label>
            <input type="text" className={inputClass} placeholder="e.g. Follow-up imaging in 3 months"
              value={form.recommendations}
              onChange={(e) => setForm({ ...form, recommendations: e.target.value })} />
          </div>

          <button type="submit" disabled={submitting}
            className="w-full bg-cyan-600 text-white rounded-xl py-2.5 font-bold hover:bg-cyan-700 disabled:opacity-60 flex items-center justify-center gap-2">
            {submitting ? <><Loader2 className="w-4 h-4 animate-spin" /> Encrypting and uploading…</> : "Upload Study"}
          </button>
        </form>
      </div>
    </div>
  );
}

export default function ImagingReportsPage() {
  const [reports, setReports] = useState<ImagingReportItem[]>([]);

  const [loading, setLoading] = useState(true);
  const [selectedImage, setSelectedImage] = useState<string | null>(null);
  // Decrypted images, keyed by study id. Populated only when a study is opened.
  const [decrypted, setDecrypted] = useState<Record<string, string>>({});
  const [decrypting, setDecrypting] = useState<string | null>(null);
  const [decryptError, setDecryptError] = useState<string | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);

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


  // Reuses whatever was already decrypted for viewing, so opening then saving
  // a scan does not decrypt it twice.
  const handleDownloadImage = async (report: ImagingReportItem) => {
    setDecryptError(null);
    let data = decrypted[report.id];
    if (!data) {
      setDecrypting(report.id);
      try {
        data = (await getImagingImage(report.id)).image_data;
        setDecrypted((prev) => ({ ...prev, [report.id]: data as string }));
      } catch (err) {
        setDecryptError(err instanceof Error ? err.message : "Failed to decrypt image");
        return;
      } finally {
        setDecrypting(null);
      }
    }
    const a = document.createElement("a");
    a.href = data;
    a.download = `${report.exam_type || "scan"}_${report.scan_region || report.id}`.replace(/\s+/g, "_");
    document.body.appendChild(a);
    a.click();
    a.remove();
  };

  useEffect(() => {
    const fetchReports = async () => {
      try {
        const data = await getImagingReports();
        setReports(data);
      } catch (error) {
        console.error(error);
        // No placeholder studies. These previously used stock photographs as
        // stand-in medical scans, which is indefensible in a clinical record.
        setReports([]);
        setDecryptError("Could not load imaging reports. Check that the backend is running.");
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
        <button
          onClick={() => setUploadOpen(true)}
          className="flex items-center gap-2 px-5 py-2.5 bg-cyan-600 hover:bg-cyan-700 text-white rounded-xl text-sm font-bold shadow-sm transition-colors"
        >
          <Plus className="w-4 h-4" /> Upload Study
        </button>
      </div>

      {uploadOpen && (
        <UploadImagingModal
          onClose={() => setUploadOpen(false)}
          onUploaded={() => {
            setLoading(true);
            getImagingReports()
              .then(setReports)
              .catch(() => setDecryptError("Uploaded, but the list could not be refreshed."))
              .finally(() => setLoading(false));
          }}
        />
      )}

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
                  {report.has_image && (
                    <button
                      onClick={() => handleDownloadImage(report)}
                      disabled={decrypting === report.id}
                      className="p-2 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600 transition-colors disabled:opacity-50"
                      title="Decrypt and download the scan"
                    >
                      {decrypting === report.id
                        ? <Loader2 className="w-4 h-4 animate-spin" />
                        : <Download className="w-4 h-4" />}
                    </button>
                  )}
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
