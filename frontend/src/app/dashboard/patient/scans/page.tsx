"use client";

import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Film, Lock, Loader2, X, ShieldCheck, Activity, User } from "lucide-react";
import { getPatientImaging, getPatientImagingImage } from "@/lib/session";

interface ImagingStudy {
  id: string;
  technician_name?: string | null;
  scan_region?: string | null;
  exam_type?: string | null;
  clinical_history?: string | null;
  findings?: string | null;
  impression?: string | null;
  recommendations?: string | null;
  has_image: boolean;
  document_hash?: string | null;
  kem_algorithm?: string | null;
  signature_algorithm?: string | null;
  blockchain_tx_hash?: string | null;
  created_at?: string | null;
}

export default function PatientScansPage() {
  const [studies, setStudies] = useState<ImagingStudy[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [opening, setOpening] = useState<string | null>(null);
  const [viewing, setViewing] = useState<{ study: ImagingStudy; image: string } | null>(null);

  useEffect(() => {
    getPatientImaging()
      .then(setStudies)
      .catch((error) => {
        console.error(error);
        setStudies([]);
        setLoadError("Could not load your scans. Check that the backend is running.");
      })
      .finally(() => setLoading(false));
  }, []);

  const open = async (study: ImagingStudy) => {
    setLoadError("");
    setOpening(study.id);
    try {
      const { image_data } = await getPatientImagingImage(study.id);
      setViewing({ study, image: image_data });
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "Could not open that scan.");
    } finally {
      setOpening(null);
    }
  };

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto space-y-4">
        <div className="h-8 w-48 bg-slate-200 animate-pulse rounded-md" />
        {[1, 2].map((i) => <div key={i} className="h-40 bg-slate-200 animate-pulse rounded-2xl" />)}
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-xl md:text-2xl font-bold text-slate-800">My Scans</h1>
        <p className="text-slate-500 mt-1">
          X-rays, MRI, CT and ultrasound studies taken during your care.
        </p>
      </motion.div>

      {loadError && (
        <div className="p-3 rounded-xl bg-rose-50 border border-rose-100 text-rose-700 text-sm font-semibold">
          {loadError}
        </div>
      )}

      {studies.length === 0 && !loadError ? (
        <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-12 text-center">
          <Film className="w-14 h-14 mx-auto text-slate-300 mb-4" />
          <h3 className="text-lg font-bold text-slate-700">No Scans Yet</h3>
          <p className="text-slate-500 mt-1">
            Imaging studies appear here once radiology has completed one for you.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {studies.map((s, idx) => (
            <motion.div
              key={s.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.05 }}
              className="bg-white rounded-2xl shadow-sm border border-slate-100 p-5"
            >
              <div className="flex flex-col sm:flex-row sm:items-start gap-4">
                <div className="w-11 h-11 rounded-full bg-slate-900 text-slate-300 flex items-center justify-center flex-shrink-0">
                  <Film className="w-5 h-5" />
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap mb-1">
                    <h3 className="text-base font-bold text-slate-800">{s.exam_type}</h3>
                    {s.signature_algorithm && (
                      <span className="text-[10px] font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded flex items-center gap-1">
                        <ShieldCheck className="w-3 h-3" /> Signed
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-slate-600 flex items-center gap-1.5">
                    <Activity className="w-3.5 h-3.5 text-slate-400" />
                    Region: <span className="font-semibold">{s.scan_region}</span>
                  </p>
                  {s.technician_name && (
                    <p className="text-xs text-slate-400 mt-0.5 flex items-center gap-1.5">
                      <User className="w-3 h-3" /> {s.technician_name}
                    </p>
                  )}
                  <p className="text-[11px] text-slate-400 mt-1">
                    {s.created_at ? new Date(s.created_at).toLocaleString() : "—"}
                  </p>

                  {/* The impression is what a patient actually reads a scan
                      report for, so it leads rather than sitting under findings. */}
                  {s.impression && (
                    <div className="mt-3 p-3 rounded-xl bg-slate-50 border border-slate-100">
                      <p className="text-[10px] uppercase font-bold text-slate-400 tracking-wide mb-1">
                        Impression
                      </p>
                      <p className="text-sm font-semibold text-slate-800">{s.impression}</p>
                    </div>
                  )}
                  {s.findings && (
                    <p className="text-sm text-slate-600 mt-2">
                      <span className="font-semibold text-slate-700">Findings: </span>
                      {s.findings}
                    </p>
                  )}
                </div>

                <div className="flex-shrink-0">
                  {s.has_image ? (
                    <button
                      onClick={() => open(s)}
                      disabled={opening === s.id}
                      className="flex items-center gap-2 px-4 py-2.5 bg-cyan-600 hover:bg-cyan-700 text-white rounded-xl text-sm font-bold transition-colors disabled:opacity-60"
                    >
                      {opening === s.id
                        ? <><Loader2 className="w-4 h-4 animate-spin" /> Decrypting…</>
                        : <><Lock className="w-4 h-4" /> View Scan</>}
                    </button>
                  ) : (
                    <span className="text-xs font-semibold text-slate-400">No image stored</span>
                  )}
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      )}

      {viewing && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-3xl max-h-[92vh] overflow-y-auto">
            <div className="flex justify-between items-start gap-4 p-5 border-b border-slate-100">
              <div>
                <h3 className="text-lg font-bold text-slate-800">{viewing.study.exam_type}</h3>
                <p className="text-sm text-slate-500">
                  {viewing.study.scan_region}
                  {viewing.study.created_at ? ` · ${new Date(viewing.study.created_at).toLocaleDateString()}` : ""}
                </p>
              </div>
              <button onClick={() => setViewing(null)} className="flex-shrink-0" aria-label="Close">
                <X className="w-5 h-5 text-slate-500" />
              </button>
            </div>

            <div className="bg-slate-900 flex items-center justify-center p-4">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={viewing.image}
                alt={`${viewing.study.exam_type} of ${viewing.study.scan_region}`}
                className="max-h-[55vh] w-auto object-contain"
              />
            </div>

            <div className="p-5 space-y-3">
              {viewing.study.clinical_history && (
                <div>
                  <p className="text-[10px] uppercase font-bold text-slate-400 tracking-wide">Clinical history</p>
                  <p className="text-sm text-slate-700">{viewing.study.clinical_history}</p>
                </div>
              )}
              {viewing.study.recommendations && (
                <div>
                  <p className="text-[10px] uppercase font-bold text-slate-400 tracking-wide">Recommendations</p>
                  <p className="text-sm text-slate-700">{viewing.study.recommendations}</p>
                </div>
              )}

              {(viewing.study.document_hash || viewing.study.blockchain_tx_hash) && (
                <div className="pt-3 border-t border-slate-100 space-y-1.5">
                  <p className="text-[10px] uppercase font-bold text-slate-400 tracking-wide">
                    Verified provenance
                  </p>
                  {viewing.study.signature_algorithm && (
                    <p className="text-xs text-slate-600">
                      Signed with <span className="font-semibold">{viewing.study.signature_algorithm}</span>
                      {viewing.study.kem_algorithm && (
                        <> · key protected with <span className="font-semibold">{viewing.study.kem_algorithm}</span></>
                      )}
                    </p>
                  )}
                  {viewing.study.document_hash && (
                    <p className="text-[11px] font-mono text-slate-400 break-all">
                      SHA-256 {viewing.study.document_hash}
                    </p>
                  )}
                  {viewing.study.blockchain_tx_hash && (
                    <p className="text-[11px] font-mono text-slate-400 break-all">
                      Anchor {viewing.study.blockchain_tx_hash}
                    </p>
                  )}
                  <p className="text-[11px] text-slate-500 pt-1">
                    Its digest was re-checked against the value recorded when the study was signed.
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
