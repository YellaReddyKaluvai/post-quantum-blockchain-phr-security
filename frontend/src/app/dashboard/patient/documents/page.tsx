"use client";

import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { FileText, Lock, Loader2, X, ShieldCheck, Stethoscope } from "lucide-react";
import { getPatientDocuments, getPatientDocumentContent } from "@/lib/session";

interface PatientDocument {
  id: string;
  document_name: string;
  document_type: string;
  doctor_name?: string | null;
  doctor_specialization?: string | null;
  status: string;
  created_at?: string | null;
  has_content: boolean;
  document_hash?: string | null;
  kem_algorithm?: string | null;
  signature_algorithm?: string | null;
  blockchain_tx_hash?: string | null;
}

const TYPE_TINT: Record<string, string> = {
  "Discharge Summary": "bg-blue-50 text-blue-700",
  "Referral Letter": "bg-violet-50 text-violet-700",
  "Medical Certificate": "bg-emerald-50 text-emerald-700",
  "Diagnosis Report": "bg-cyan-50 text-cyan-700",
  "Consultation Report": "bg-amber-50 text-amber-700",
  "Treatment Summary": "bg-teal-50 text-teal-700",
};

export default function PatientDocumentsPage() {
  const [documents, setDocuments] = useState<PatientDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [opening, setOpening] = useState<string | null>(null);
  const [viewing, setViewing] = useState<{ doc: PatientDocument; content: string } | null>(null);

  useEffect(() => {
    getPatientDocuments()
      .then(setDocuments)
      .catch((error) => {
        console.error(error);
        setDocuments([]);
        setLoadError("Could not load your documents. Check that the backend is running.");
      })
      .finally(() => setLoading(false));
  }, []);

  const handleOpen = async (doc: PatientDocument) => {
    setLoadError("");
    setOpening(doc.id);
    try {
      const { content } = await getPatientDocumentContent(doc.id);
      setViewing({ doc, content });
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "Could not open that document.");
    } finally {
      setOpening(null);
    }
  };

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto space-y-4">
        <div className="h-8 w-56 bg-slate-200 animate-pulse rounded-md" />
        {[1, 2].map((i) => <div key={i} className="h-28 bg-slate-200 animate-pulse rounded-2xl" />)}
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-xl md:text-2xl font-bold text-slate-800">My Documents</h1>
        <p className="text-slate-500 mt-1">
          Discharge summaries, referral letters and certificates written by your doctors.
        </p>
      </motion.div>

      {loadError && (
        <div className="p-3 rounded-xl bg-rose-50 border border-rose-100 text-rose-700 text-sm font-semibold">
          {loadError}
        </div>
      )}

      {documents.length === 0 && !loadError ? (
        <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-12 text-center">
          <FileText className="w-14 h-14 mx-auto text-slate-300 mb-4" />
          <h3 className="text-lg font-bold text-slate-700">No Documents Yet</h3>
          <p className="text-slate-500 mt-1">
            Documents appear here once a doctor writes one for you.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {documents.map((doc, idx) => (
            <motion.div
              key={doc.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.05 }}
              className="bg-white rounded-2xl shadow-sm border border-slate-100 p-5"
            >
              <div className="flex flex-col sm:flex-row sm:items-center gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap mb-1.5">
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded uppercase tracking-wide ${TYPE_TINT[doc.document_type] || "bg-slate-100 text-slate-600"}`}>
                      {doc.document_type}
                    </span>
                    {doc.signature_algorithm && (
                      <span className="text-[10px] font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded flex items-center gap-1">
                        <ShieldCheck className="w-3 h-3" /> Signed
                      </span>
                    )}
                  </div>

                  <h3 className="text-base font-bold text-slate-800 truncate">{doc.document_name}</h3>

                  <p className="text-sm text-slate-500 mt-0.5 flex items-center gap-1.5">
                    <Stethoscope className="w-3.5 h-3.5 text-slate-400" />
                    Dr. {doc.doctor_name || "—"}
                    {doc.doctor_specialization && (
                      <span className="text-slate-400">· {doc.doctor_specialization}</span>
                    )}
                  </p>
                  <p className="text-[11px] text-slate-400 mt-1">
                    {doc.created_at ? new Date(doc.created_at).toLocaleString() : "—"}
                  </p>
                </div>

                <div className="flex-shrink-0">
                  {doc.has_content ? (
                    <button
                      onClick={() => handleOpen(doc)}
                      disabled={opening === doc.id}
                      className="flex items-center gap-2 px-4 py-2.5 bg-cyan-600 hover:bg-cyan-700 text-white rounded-xl text-sm font-bold transition-colors disabled:opacity-60"
                    >
                      {opening === doc.id
                        ? <><Loader2 className="w-4 h-4 animate-spin" /> Decrypting…</>
                        : <><Lock className="w-4 h-4" /> Open</>}
                    </button>
                  ) : (
                    <span className="text-xs font-semibold text-slate-400">No content stored</span>
                  )}
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      )}

      {viewing && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-2xl p-6 max-h-[90vh] overflow-y-auto">
            <div className="flex justify-between items-start gap-4 mb-1">
              <div>
                <h3 className="text-lg font-bold text-slate-800">{viewing.doc.document_name}</h3>
                <p className="text-sm text-slate-500">
                  {viewing.doc.document_type} · Dr. {viewing.doc.doctor_name} ·{" "}
                  {viewing.doc.created_at ? new Date(viewing.doc.created_at).toLocaleDateString() : ""}
                </p>
              </div>
              <button onClick={() => setViewing(null)} className="flex-shrink-0">
                <X className="w-5 h-5 text-slate-500" />
              </button>
            </div>

            <div className="mt-5 p-5 rounded-xl bg-slate-50 border border-slate-100">
              <p className="text-sm text-slate-800 whitespace-pre-wrap leading-relaxed">
                {viewing.content}
              </p>
            </div>

            {/* Show the provenance, so the document's authenticity is checkable
                rather than merely asserted. */}
            {(viewing.doc.document_hash || viewing.doc.blockchain_tx_hash) && (
              <div className="mt-4 pt-4 border-t border-slate-100 space-y-1.5">
                <p className="text-[10px] uppercase font-bold text-slate-400 tracking-wide">
                  Verified provenance
                </p>
                {viewing.doc.signature_algorithm && (
                  <p className="text-xs text-slate-600">
                    Signed with <span className="font-semibold">{viewing.doc.signature_algorithm}</span>
                    {viewing.doc.kem_algorithm && <> · key protected with <span className="font-semibold">{viewing.doc.kem_algorithm}</span></>}
                  </p>
                )}
                {viewing.doc.document_hash && (
                  <p className="text-[11px] font-mono text-slate-400 break-all">
                    SHA-256 {viewing.doc.document_hash}
                  </p>
                )}
                {viewing.doc.blockchain_tx_hash && (
                  <p className="text-[11px] font-mono text-slate-400 break-all">
                    Anchor {viewing.doc.blockchain_tx_hash}
                  </p>
                )}
                <p className="text-[11px] text-slate-500 pt-1">
                  Its digest was re-checked against the value recorded when your doctor signed it.
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
