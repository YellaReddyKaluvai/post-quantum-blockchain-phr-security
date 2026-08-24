"use client";

import React, { useEffect, useState, useCallback } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  Shield, CheckCircle, Fingerprint, Lock, Loader2, Hospital,
  AlertTriangle, User, Stethoscope, FlaskConical,
} from "lucide-react";
import {
  getLabTestRequestDetail, getLabReportTemplate, createStructuredLabReport,
} from "@/lib/session";

interface Analyte {
  key: string;
  name: string;
  unit: string;
  input: string;
  step?: string;
  options?: string[];
  ref?: Record<string, [number | null, number | null, string]>;
  indent?: boolean;
  computed?: string;
  note?: string;
  default?: string;
}

interface NarrativeField {
  key: string;
  label: string;
  input: string;
  options?: string[];
  placeholder?: string;
  required?: boolean;
  rows?: number;
}

interface Panel {
  code: string;
  name: string;
  short_name: string;
  category: string;
  layout: "tabular" | "narrative";
  specimen: string;
  method: string;
  sections?: { title: string; analytes?: Analyte[]; fields?: NarrativeField[] }[];
  measurements?: Analyte[];
}

interface RequestDetail {
  id: string;
  test_name: string;
  panel_code?: string;
  priority: string;
  status: string;
  clinical_notes?: string;
  report_id?: string;
  report_no?: string;
  patient: {
    id: string; user_id: string; full_name: string; gender?: string;
    age_display?: string; blood_group?: string; pqc_ready: boolean;
  };
  doctor?: { full_name?: string; user_id?: string; specialization?: string } | null;
}

type SecurityStep = 0 | 1 | 2 | 3 | 4 | 5 | 6;

export default function CreateReportPage() {
  const params = useSearchParams();
  const router = useRouter();
  const reqId = params.get("reqId");

  const [request, setRequest] = useState<RequestDetail | null>(null);
  const [panel, setPanel] = useState<Panel | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [remarks, setRemarks] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [securityStep, setSecurityStep] = useState<SecurityStep>(0);
  const [submitError, setSubmitError] = useState("");
  const [result, setResult] = useState<{ report_no: string; document_hash: string; blockchain_tx_hash?: string } | null>(null);

  const load = useCallback(async () => {
    if (!reqId) {
      setLoadError("No test request selected. Open this page from Test Requests.");
      setLoading(false);
      return;
    }
    setLoading(true);
    setLoadError("");
    try {
      const req: RequestDetail = await getLabTestRequestDetail(reqId);
      setRequest(req);

      if (req.status === "Completed") {
        setLoadError("This request has already been completed and its report finalized.");
        setLoading(false);
        return;
      }
      if (!req.patient.pqc_ready) {
        setLoadError("Patient has no post-quantum encryption key on record; the report cannot be secured.");
        setLoading(false);
        return;
      }
      if (!req.panel_code) {
        setLoadError("This request has no investigation panel assigned. Ask the referring doctor to specify one.");
        setLoading(false);
        return;
      }

      const tmpl: Panel = await getLabReportTemplate(req.panel_code);
      setPanel(tmpl);

      // Pre-fill defaults (e.g. "Negative", "Nil") so the technician only edits abnormals.
      const defaults: Record<string, string> = {};
      const collectDefaults = (analytes?: Analyte[]) => {
        (analytes || []).forEach((a) => {
          if (a.default) defaults[a.key] = a.default;
        });
      };
      tmpl.sections?.forEach((s) => collectDefaults(s.analytes));
      setValues(defaults);
    } catch (e) {
      console.error(e);
      setLoadError(e instanceof Error ? e.message : "Failed to load the test request.");
    } finally {
      setLoading(false);
    }
  }, [reqId]);

  useEffect(() => {
    load();
  }, [load]);

  const setValue = (key: string, v: string) => setValues((prev) => ({ ...prev, [key]: v }));

  const isTabular = panel?.layout === "tabular";
  const allAnalytes: Analyte[] = isTabular
    ? (panel?.sections || []).flatMap((s) => s.analytes || [])
    : (panel?.measurements || []);
  const filledCount = allAnalytes.filter((a) => (values[a.key] || "").trim() !== "").length;
  const canSubmit = !!panel && !!reqId && filledCount > 0 && !submitting;

  const handleFinalize = async () => {
    if (!reqId || !panel) return;
    setSubmitError("");
    setSubmitting(true);
    setSecurityStep(1); // Rendering the report
    try {
      await new Promise((r) => setTimeout(r, 350));
      setSecurityStep(2); // Hashing
      await new Promise((r) => setTimeout(r, 300));
      setSecurityStep(3); // AES-256-GCM
      await new Promise((r) => setTimeout(r, 300));
      setSecurityStep(4); // ML-KEM
      await new Promise((r) => setTimeout(r, 300));
      setSecurityStep(5); // ML-DSA

      const res = await createStructuredLabReport({
        request_id: reqId,
        panel_code: panel.code,
        values,
        remarks: remarks || undefined,
      });

      setSecurityStep(6); // Done
      setResult({
        report_no: res.report_no,
        document_hash: res.document_hash,
        blockchain_tx_hash: res.blockchain_tx_hash,
      });
    } catch (e) {
      console.error(e);
      setSubmitError(e instanceof Error ? e.message : "Failed to finalize the report.");
      setSecurityStep(0);
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return <div className="max-w-3xl mx-auto py-20 text-center text-slate-400">Loading test request…</div>;
  }

  if (loadError) {
    return (
      <div className="max-w-2xl mx-auto py-16">
        <div className="bg-amber-50 border border-amber-200 rounded-2xl p-6 flex gap-4">
          <AlertTriangle className="w-6 h-6 text-amber-600 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold text-amber-800">Can&apos;t open this report form</p>
            <p className="text-sm text-amber-700 mt-1">{loadError}</p>
            <button
              onClick={() => router.push("/dashboard/lab-technician/requests")}
              className="mt-4 px-4 py-2 bg-white border border-amber-300 rounded-lg text-sm font-semibold text-amber-800 hover:bg-amber-100"
            >
              Back to Test Requests
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (result) {
    return (
      <div className="max-w-2xl mx-auto py-16 text-center">
        <div className="w-16 h-16 mx-auto bg-emerald-50 rounded-2xl flex items-center justify-center mb-4 border border-emerald-100">
          <CheckCircle className="w-9 h-9 text-emerald-500" />
        </div>
        <h1 className="text-2xl font-bold text-slate-800">Report Finalized &amp; Secured</h1>
        <p className="text-sm text-slate-500 mt-2">
          {panel?.short_name} report <span className="font-mono font-semibold text-slate-700">{result.report_no}</span> has
          been signed, encrypted and stored. The patient and referring doctor have been notified.
        </p>
        <div className="mt-6 text-left bg-slate-50 border border-slate-200 rounded-xl p-4 text-xs font-mono text-slate-600 break-all">
          SHA-256: {result.document_hash}
          {result.blockchain_tx_hash && <><br />Audit Tx: {result.blockchain_tx_hash}</>}
        </div>
        <div className="mt-6 flex justify-center gap-3">
          <button
            onClick={() => router.push("/dashboard/lab-technician/reports")}
            className="px-5 py-2.5 bg-cyan-600 hover:bg-cyan-700 text-white rounded-xl text-sm font-semibold"
          >
            View My Reports
          </button>
          <button
            onClick={() => router.push("/dashboard/lab-technician/requests")}
            className="px-5 py-2.5 bg-white border border-slate-200 rounded-xl text-sm font-semibold text-slate-700 hover:bg-slate-50"
          >
            Back to Requests
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-4xl mx-auto pb-24">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">{panel?.name}</h1>
        <p className="text-sm text-slate-500">{panel?.specimen} · {panel?.method}</p>
      </div>

      {/* Patient / referral context — read-only, sourced from the patient record */}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-5 grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="flex gap-3">
          <div className="w-9 h-9 rounded-lg bg-cyan-50 flex items-center justify-center flex-shrink-0">
            <User className="w-4 h-4 text-cyan-600" />
          </div>
          <div className="text-sm">
            <p className="font-semibold text-slate-800">{request?.patient.full_name}</p>
            <p className="text-slate-500">{request?.patient.user_id} · {request?.patient.age_display} · {request?.patient.gender} · {request?.patient.blood_group || "Blood group not recorded"}</p>
          </div>
        </div>
        <div className="flex gap-3">
          <div className="w-9 h-9 rounded-lg bg-slate-50 flex items-center justify-center flex-shrink-0">
            <Stethoscope className="w-4 h-4 text-slate-500" />
          </div>
          <div className="text-sm">
            <p className="font-semibold text-slate-800">{request?.doctor?.full_name ? `Dr. ${request.doctor.full_name}` : "No referring doctor"}</p>
            <p className="text-slate-500">{request?.doctor?.user_id} {request?.doctor?.specialization ? `· ${request.doctor.specialization}` : ""}</p>
          </div>
        </div>
        {request?.clinical_notes && (
          <div className="sm:col-span-2 flex gap-3 pt-2 border-t border-slate-100">
            <div className="w-9 h-9 rounded-lg bg-slate-50 flex items-center justify-center flex-shrink-0">
              <FlaskConical className="w-4 h-4 text-slate-500" />
            </div>
            <div className="text-sm">
              <p className="text-slate-500 text-xs font-semibold uppercase tracking-wide">Clinical Notes</p>
              <p className="text-slate-700">{request.clinical_notes}</p>
            </div>
          </div>
        )}
      </div>

      {/* Data entry form, driven entirely by the panel definition from the server */}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6 space-y-6">
        {isTabular
          ? panel?.sections?.map((section) => (
              <div key={section.title}>
                <h3 className="text-xs font-bold text-cyan-700 uppercase tracking-wide mb-3">{section.title}</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {(section.analytes || []).map((a) => (
                    <AnalyteInput key={a.key} analyte={a} value={values[a.key] || ""} onChange={setValue} />
                  ))}
                </div>
              </div>
            ))
          : (
            <>
              {panel?.measurements && panel.measurements.length > 0 && (
                <div>
                  <h3 className="text-xs font-bold text-cyan-700 uppercase tracking-wide mb-3">Measurements</h3>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {panel.measurements.map((a) => (
                      <AnalyteInput key={a.key} analyte={a} value={values[a.key] || ""} onChange={setValue} />
                    ))}
                  </div>
                </div>
              )}
              {panel?.sections?.map((section) => (
                <div key={section.title}>
                  <h3 className="text-xs font-bold text-cyan-700 uppercase tracking-wide mb-3">{section.title}</h3>
                  <div className="space-y-4">
                    {(section.fields || []).map((f) => (
                      <NarrativeInput key={f.key} field={f} value={values[f.key] || ""} onChange={setValue} />
                    ))}
                  </div>
                </div>
              ))}
            </>
          )}

        <div className="pt-4 border-t border-slate-100">
          <label className="block text-sm font-medium text-slate-700 mb-1">Technical Remarks (Optional)</label>
          <textarea
            rows={3}
            value={remarks}
            onChange={(e) => setRemarks(e.target.value)}
            className="w-full px-3 py-2 bg-white border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-cyan-500/20 focus:border-cyan-500"
            placeholder="Any additional technical observations for this specimen..."
          />
        </div>
      </div>

      {submitError && (
        <div className="flex items-center gap-2 px-4 py-3 bg-rose-50 border border-rose-100 rounded-xl text-sm text-rose-700">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" /> {submitError}
        </div>
      )}

      <button
        onClick={handleFinalize}
        disabled={!canSubmit}
        className="w-full flex items-center justify-center gap-2 px-6 py-4 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 text-white font-bold rounded-xl shadow-lg shadow-emerald-600/20 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <Shield className="w-5 h-5" />
        Finalize &amp; Secure Report ({filledCount} result{filledCount === 1 ? "" : "s"} entered)
      </button>

      <AnimatePresence>
        {submitting && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="absolute inset-0 bg-slate-900/60 backdrop-blur-sm" />
            <motion.div initial={{ opacity: 0, scale: 0.95, y: 20 }} animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              className="relative bg-white rounded-2xl shadow-2xl p-8 max-w-sm w-full overflow-hidden">
              <div className="absolute top-0 left-0 w-full h-1 bg-slate-100">
                <motion.div className="h-full bg-cyan-500" initial={{ width: "0%" }}
                  animate={{ width: `${(securityStep / 6) * 100}%` }} transition={{ duration: 0.4 }} />
              </div>
              <div className="text-center mb-6">
                <div className="w-16 h-16 mx-auto bg-cyan-50 rounded-2xl flex items-center justify-center mb-4 border border-cyan-100">
                  {securityStep < 6 ? <Shield className="w-8 h-8 text-cyan-500 animate-pulse" /> : <CheckCircle className="w-8 h-8 text-emerald-500" />}
                </div>
                <h3 className="text-lg font-bold text-slate-800">Securing Report</h3>
                <p className="text-xs text-slate-500 mt-1">Hybrid Post-Quantum Cryptography Pipeline</p>
              </div>
              <div className="space-y-4 text-sm">
                <Step icon={Hospital} label="Rendering Hospital-Format Document" active={securityStep === 1} done={securityStep > 1} />
                <Step icon={Fingerprint} label="SHA-256 Document Hashing" active={securityStep === 2} done={securityStep > 2} />
                <Step icon={Lock} label="AES-256-GCM Encryption" active={securityStep === 3} done={securityStep > 3} />
                <Step icon={Shield} label="ML-KEM-768 Key Encapsulation" active={securityStep === 4} done={securityStep > 4} />
                <Step icon={Fingerprint} label="ML-DSA-65 Digital Signature" active={securityStep === 5} done={securityStep > 5} />
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}

function Step({ icon: Icon, label, active, done }: { icon: React.ElementType; label: string; active: boolean; done: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <div className={`w-6 h-6 rounded-full flex items-center justify-center ${done ? "bg-emerald-100 text-emerald-600" : active ? "bg-cyan-100 text-cyan-600" : "bg-slate-100 text-slate-400"}`}>
        {done ? <CheckCircle className="w-4 h-4" /> : active ? <Loader2 className="w-4 h-4 animate-spin" /> : <Icon className="w-4 h-4" />}
      </div>
      <span className={done ? "text-slate-800 font-medium" : active ? "text-cyan-700 font-semibold" : "text-slate-400"}>{label}</span>
    </div>
  );
}

function refDisplay(analyte: Analyte): string {
  const ref = analyte.ref;
  if (!ref) return "";
  const entry = ref["A"] || ref["M"] || ref["F"];
  return entry?.[2] || "";
}

function AnalyteInput({ analyte, value, onChange }: { analyte: Analyte; value: string; onChange: (k: string, v: string) => void }) {
  const ref = refDisplay(analyte);
  const label = (
    <label className={`block text-sm font-medium text-slate-700 mb-1 ${analyte.indent ? "pl-4" : ""}`}>
      {analyte.name} {analyte.computed && <span className="text-[10px] text-slate-400 font-normal">(auto-calculated if left blank)</span>}
    </label>
  );

  if (analyte.input === "select") {
    return (
      <div>
        {label}
        <select
          value={value}
          onChange={(e) => onChange(analyte.key, e.target.value)}
          className="w-full px-3 py-2 bg-white border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-cyan-500/20 focus:border-cyan-500"
        >
          <option value="">Select…</option>
          {(analyte.options || []).map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
        {ref && <p className="text-[10px] text-slate-400 mt-1">Expected: {ref}</p>}
      </div>
    );
  }

  return (
    <div>
      {label}
      <div className="flex gap-2 items-center">
        <input
          type={analyte.input === "number" ? "number" : "text"}
          step={analyte.step || "any"}
          value={value}
          onChange={(e) => onChange(analyte.key, e.target.value)}
          placeholder={analyte.computed ? "auto" : "Enter result"}
          className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-cyan-500/20 focus:border-cyan-500"
        />
        {analyte.unit && <span className="text-xs text-slate-500 w-20 flex-shrink-0">{analyte.unit}</span>}
      </div>
      {ref && <p className="text-[10px] text-slate-400 mt-1">Ref: {ref}</p>}
      {analyte.note && <p className="text-[10px] text-slate-400 mt-0.5">{analyte.note}</p>}
    </div>
  );
}

function NarrativeInput({ field, value, onChange }: { field: NarrativeField; value: string; onChange: (k: string, v: string) => void }) {
  return (
    <div>
      <label className="block text-sm font-medium text-slate-700 mb-1">
        {field.label} {field.required && <span className="text-rose-500">*</span>}
      </label>
      {field.input === "select" ? (
        <select
          value={value}
          onChange={(e) => onChange(field.key, e.target.value)}
          className="w-full px-3 py-2 bg-white border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-cyan-500/20 focus:border-cyan-500"
        >
          <option value="">Select…</option>
          {(field.options || []).map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      ) : field.input === "text" ? (
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(field.key, e.target.value)}
          placeholder={field.placeholder}
          className="w-full px-3 py-2 bg-white border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-cyan-500/20 focus:border-cyan-500"
        />
      ) : (
        <textarea
          rows={field.rows || 4}
          value={value}
          onChange={(e) => onChange(field.key, e.target.value)}
          placeholder={field.placeholder}
          className="w-full px-3 py-2 bg-white border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-cyan-500/20 focus:border-cyan-500"
        />
      )}
    </div>
  );
}
