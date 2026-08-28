"use client";

import React, { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import { motion } from "framer-motion";
import { User, Activity, FileText, ChevronLeft, Plus, X, FlaskConical, CheckCircle, HeartPulse } from "lucide-react";
import Link from "next/link";
import {
  getDoctorPatientDetail, createDiagnosis, createPrescription,
  getDoctorLabPanels, requestLabTest,
} from "@/lib/session";

interface LabPanel {
  code: string;
  name: string;
  short_name: string;
  category: string;
}

interface PatientProfileInfo {
  id: string;
  user_id?: string;
  full_name?: string;
  email?: string;
  gender?: string;
  blood_group?: string;
  date_of_birth?: string;
}

interface DiagnosisEntry {
  id: string;
  title: string;
  description?: string | null;
  symptoms?: string | null;
  doctor_notes?: string | null;
  recommended_tests?: string | null;
  visit_date?: string | null;
  created_at?: string | null;
}

interface PrescriptionEntry {
  id: string;
  medicine_name: string;
  dosage: string;
  frequency: string;
  duration: string;
  instructions?: string | null;
  prescribed_date?: string | null;
}

interface VitalsEntry {
  id: string;
  temperature_celsius?: number | null;
  blood_pressure_systolic?: number | null;
  blood_pressure_diastolic?: number | null;
  heart_rate?: number | null;
  spo2?: number | null;
  respiratory_rate?: number | null;
  notes?: string | null;
  recorded_at?: string | null;
  nurse_name?: string | null;
}

interface NursingNoteEntry {
  id: string;
  note_type: string;
  content: string;
  created_at?: string | null;
  nurse_name?: string | null;
}

interface PatientDetailResponse {
  profile: PatientProfileInfo;
  diagnoses: DiagnosisEntry[];
  prescriptions: PrescriptionEntry[];
  vitals: VitalsEntry[];
  nursing_notes: NursingNoteEntry[];
}

// Same thresholds the backend uses to decide whether to alert the doctor.
function isAbnormal(key: string, value: number): boolean {
  switch (key) {
    case "temperature_celsius": return value >= 38.0 || value <= 35.0;
    case "heart_rate": return value > 100 || value < 50;
    case "spo2": return value < 92;
    case "blood_pressure_systolic": return value > 140 || value < 90;
    case "blood_pressure_diastolic": return value > 90 || value < 60;
    case "respiratory_rate": return value > 24 || value < 10;
    default: return false;
  }
}

const todayStr = () => new Date().toISOString().split("T")[0];

const emptyDiagnosisForm = {
  title: "",
  description: "",
  symptoms: "",
  doctor_notes: "",
  recommended_tests: "",
  visit_date: todayStr(),
};

const emptyPrescriptionForm = {
  medicine_name: "",
  dosage: "",
  frequency: "",
  duration: "",
  instructions: "",
  prescribed_date: todayStr(),
};


export default function PatientDetails() {
  const params = useParams();
  const [patient, setPatient] = useState<PatientDetailResponse | null>(null);

  const [loading, setLoading] = useState(true);

  const [diagnosisModal, setDiagnosisModal] = useState(false);
  const [prescriptionModal, setPrescriptionModal] = useState(false);
  const [diagnosisForm, setDiagnosisForm] = useState(emptyDiagnosisForm);
  const [prescriptionForm, setPrescriptionForm] = useState(emptyPrescriptionForm);
  const [diagnosisSubmitting, setDiagnosisSubmitting] = useState(false);
  const [prescriptionSubmitting, setPrescriptionSubmitting] = useState(false);
  const [diagnosisError, setDiagnosisError] = useState("");
  const [prescriptionError, setPrescriptionError] = useState("");

  const [labModal, setLabModal] = useState(false);
  const [labPanels, setLabPanels] = useState<LabPanel[]>([]);
  const [labForm, setLabForm] = useState({ panel_code: "", priority: "Routine", clinical_notes: "" });
  const [labSubmitting, setLabSubmitting] = useState(false);
  const [labError, setLabError] = useState("");
  const [labSuccess, setLabSuccess] = useState<{ panel: string; priority: string } | null>(null);

  const fetchDetail = useCallback(async () => {
    try {
      const data = await getDoctorPatientDetail(params.id as string);
      setPatient(data);
    } catch (error) {
      console.error("Error fetching patient detail:", error);
    } finally {
      setLoading(false);
    }
  }, [params.id]);

  useEffect(() => {
    fetchDetail();
  }, [fetchDetail]);

  const openLabModal = async () => {
    setLabModal(true);
    setLabSuccess(null);
    setLabError("");
    if (labPanels.length === 0) {
      try {
        setLabPanels(await getDoctorLabPanels());
      } catch (e) {
        console.error(e);
      }
    }
  };

  const handleRequestTest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!labForm.panel_code) return;
    setLabSubmitting(true);
    setLabError("");
    try {
      const panel = labPanels.find((p) => p.code === labForm.panel_code);
      await requestLabTest({
        patient_id: params.id as string,
        panel_code: labForm.panel_code,
        priority: labForm.priority,
        clinical_notes: labForm.clinical_notes || undefined,
      });
      setLabSuccess({ panel: panel?.short_name || labForm.panel_code, priority: labForm.priority });
      setLabForm({ panel_code: "", priority: "Routine", clinical_notes: "" });
    } catch (error) {
      console.error(error);
      setLabError(error instanceof Error ? error.message : "Failed to request the test");
    } finally {
      setLabSubmitting(false);
    }
  };

  const handleDiagnosis = async (e: React.FormEvent) => {
    e.preventDefault();
    setDiagnosisError("");
    setDiagnosisSubmitting(true);
    try {
      await createDiagnosis(params.id as string, {
        title: diagnosisForm.title,
        description: diagnosisForm.description || undefined,
        symptoms: diagnosisForm.symptoms || undefined,
        doctor_notes: diagnosisForm.doctor_notes || undefined,
        recommended_tests: diagnosisForm.recommended_tests || undefined,
        visit_date: diagnosisForm.visit_date,
      });
      setDiagnosisModal(false);
      setDiagnosisForm(emptyDiagnosisForm);
      await fetchDetail();
    } catch (error) {
      setDiagnosisError(error instanceof Error ? error.message : "Failed to create diagnosis.");
    } finally {
      setDiagnosisSubmitting(false);
    }
  };

  const handlePrescription = async (e: React.FormEvent) => {
    e.preventDefault();
    setPrescriptionError("");
    setPrescriptionSubmitting(true);
    try {
      await createPrescription(params.id as string, {
        medicine_name: prescriptionForm.medicine_name,
        dosage: prescriptionForm.dosage,
        frequency: prescriptionForm.frequency,
        duration: prescriptionForm.duration,
        instructions: prescriptionForm.instructions || undefined,
        prescribed_date: prescriptionForm.prescribed_date,
      });
      setPrescriptionModal(false);
      setPrescriptionForm(emptyPrescriptionForm);
      await fetchDetail();
    } catch (error) {
      setPrescriptionError(error instanceof Error ? error.message : "Failed to create prescription.");
    } finally {
      setPrescriptionSubmitting(false);
    }
  };

  if (loading) {
    return <div className="h-96 bg-slate-200 animate-pulse rounded-2xl" />;
  }

  if (!patient) {
    return <div className="text-center p-6 text-slate-500">Patient not found.</div>;
  }

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <Link href="/dashboard/doctor/patients" className="flex items-center gap-2 text-slate-500 hover:text-slate-800 transition-colors">
        <ChevronLeft className="w-4 h-4" />
        Back to Patients
      </Link>

      {/* Top Section */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100 flex flex-col md:flex-row gap-6 items-center md:items-start">
        <div className="w-24 h-24 rounded-full bg-cyan-100 flex items-center justify-center flex-shrink-0">
          <User className="w-10 h-10 text-cyan-600" />
        </div>
        <div className="flex-1 grid grid-cols-2 md:grid-cols-4 gap-4 w-full">
          <div>
            <p className="text-xs text-slate-400 uppercase tracking-wider">Name</p>
            <p className="text-lg font-bold text-slate-800">{patient.profile.full_name || "Unknown"}</p>
          </div>
          <div>
            <p className="text-xs text-slate-400 uppercase tracking-wider">Email</p>
            <p className="text-sm font-medium text-slate-700">{patient.profile.email || "N/A"}</p>
          </div>
          <div>
            <p className="text-xs text-slate-400 uppercase tracking-wider">Gender</p>
            <p className="text-sm font-medium text-slate-700">{patient.profile.gender || "N/A"}</p>
          </div>
          <div>
            <p className="text-xs text-slate-400 uppercase tracking-wider">Blood Group</p>
            <p className="text-sm font-medium text-slate-700">{patient.profile.blood_group || "N/A"}</p>
          </div>
          <div>
            <p className="text-xs text-slate-400 uppercase tracking-wider">DOB</p>
            <p className="text-sm font-medium text-slate-700">{patient.profile.date_of_birth || "N/A"}</p>
          </div>
        </div>
        <div className="flex flex-col gap-2 w-full md:w-auto">
          <button onClick={() => setDiagnosisModal(true)} className="flex items-center justify-center gap-2 px-4 py-2 bg-cyan-600 hover:bg-cyan-700 text-white rounded-xl text-sm font-bold transition-colors">
            <Plus className="w-4 h-4" /> New Diagnosis
          </button>
          <button onClick={() => setPrescriptionModal(true)} className="flex items-center justify-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-sm font-bold transition-colors">
            <Plus className="w-4 h-4" /> New Prescription
          </button>
          <button onClick={openLabModal} className="flex items-center justify-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-sm font-bold transition-colors">
            <FlaskConical className="w-4 h-4" /> Request Lab Test
          </button>
        </div>
      </motion.div>

      {/* Nursing observations — recorded by nurses, read here by the treating doctor */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}
        className="bg-white rounded-2xl shadow-sm border border-slate-100 p-6">
        <div className="flex items-center gap-3 mb-5 border-b border-slate-100 pb-4">
          <HeartPulse className="w-5 h-5 text-rose-500" />
          <h2 className="text-lg font-bold text-slate-800">Nursing Observations</h2>
          {patient.vitals?.[0]?.recorded_at && (
            <span className="ml-auto text-xs text-slate-400">
              Last reading {new Date(patient.vitals[0].recorded_at).toLocaleString()}
              {patient.vitals[0].nurse_name ? ` · ${patient.vitals[0].nurse_name}` : ""}
            </span>
          )}
        </div>

        {!patient.vitals || patient.vitals.length === 0 ? (
          <p className="text-sm text-slate-500">No vitals recorded by nursing staff.</p>
        ) : (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-5">
              {([
                { key: "temperature_celsius", label: "Temp", unit: "°C" },
                { key: "heart_rate", label: "Heart Rate", unit: "bpm" },
                { key: "spo2", label: "SpO₂", unit: "%" },
                { key: "blood_pressure_systolic", label: "BP Sys", unit: "mmHg" },
                { key: "blood_pressure_diastolic", label: "BP Dia", unit: "mmHg" },
                { key: "respiratory_rate", label: "Resp", unit: "/min" },
              ] as const).map((c) => {
                const v = patient.vitals[0][c.key] as number | null | undefined;
                const has = v !== null && v !== undefined;
                const abnormal = has && isAbnormal(c.key, Number(v));
                return (
                  <div key={c.key} className={`p-3 rounded-xl border ${abnormal ? "bg-amber-50 border-amber-200" : "bg-slate-50 border-slate-100"}`}>
                    <p className="text-[10px] uppercase font-bold text-slate-400 tracking-wide">{c.label}</p>
                    <p className={`text-lg font-bold tabular-nums ${abnormal ? "text-amber-700" : "text-slate-800"}`}>
                      {has ? v : "—"}{has && <span className="text-xs font-medium ml-0.5">{c.unit}</span>}
                    </p>
                    {abnormal && <p className="text-[10px] font-bold text-amber-600 mt-0.5">Out of range</p>}
                  </div>
                );
              })}
            </div>

            {patient.vitals.length > 1 && (
              <details className="group">
                <summary className="cursor-pointer text-xs font-bold text-slate-500 hover:text-slate-700 select-none">
                  Show {patient.vitals.length - 1} earlier reading{patient.vitals.length > 2 ? "s" : ""}
                </summary>
                <div className="overflow-x-auto mt-3">
                  <table className="w-full text-sm min-w-[560px]">
                    <thead>
                      <tr className="text-left text-[10px] uppercase tracking-wide text-slate-400 border-b border-slate-100">
                        <th className="py-2 pr-4 font-bold">Recorded</th>
                        <th className="py-2 pr-4 font-bold">Temp</th>
                        <th className="py-2 pr-4 font-bold">HR</th>
                        <th className="py-2 pr-4 font-bold">SpO₂</th>
                        <th className="py-2 pr-4 font-bold">BP</th>
                        <th className="py-2 font-bold">By</th>
                      </tr>
                    </thead>
                    <tbody className="tabular-nums">
                      {patient.vitals.slice(1).map((v) => (
                        <tr key={v.id} className="border-b border-slate-50 last:border-0">
                          <td className="py-2 pr-4 text-slate-600 whitespace-nowrap">
                            {v.recorded_at ? new Date(v.recorded_at).toLocaleString() : "—"}
                          </td>
                          <td className="py-2 pr-4 text-slate-800">{v.temperature_celsius ?? "—"}</td>
                          <td className="py-2 pr-4 text-slate-800">{v.heart_rate ?? "—"}</td>
                          <td className="py-2 pr-4 text-slate-800">{v.spo2 ?? "—"}</td>
                          <td className="py-2 pr-4 text-slate-800">
                            {v.blood_pressure_systolic && v.blood_pressure_diastolic
                              ? `${v.blood_pressure_systolic}/${v.blood_pressure_diastolic}` : "—"}
                          </td>
                          <td className="py-2 text-slate-500">{v.nurse_name || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            )}
          </>
        )}

        {patient.nursing_notes && patient.nursing_notes.length > 0 && (
          <div className="mt-5 pt-5 border-t border-slate-100 space-y-2">
            <p className="text-xs font-bold text-slate-500 uppercase tracking-wide mb-2">Nursing Notes</p>
            {patient.nursing_notes.map((n) => (
              <div key={n.id} className="p-3 bg-slate-50 rounded-xl border border-slate-100">
                <div className="flex items-center gap-2 mb-1">
                  <span className={`text-[10px] font-bold px-2 py-0.5 rounded uppercase tracking-wide ${
                    n.note_type === "Incident" ? "bg-rose-100 text-rose-700"
                      : n.note_type === "Care" ? "bg-blue-100 text-blue-700"
                      : "bg-slate-200 text-slate-600"
                  }`}>{n.note_type}</span>
                  <span className="text-[11px] text-slate-400 ml-auto">
                    {n.created_at ? new Date(n.created_at).toLocaleString() : ""}
                  </span>
                </div>
                <p className="text-sm text-slate-700">{n.content}</p>
                {n.nurse_name && <p className="text-[11px] text-slate-400 mt-1">— {n.nurse_name}</p>}
              </div>
            ))}
          </div>
        )}
      </motion.div>

      {/* Middle Section */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="bg-white rounded-2xl shadow-sm border border-slate-100 p-6">
          <div className="flex items-center gap-3 mb-6 border-b border-slate-100 pb-4">
            <Activity className="w-5 h-5 text-indigo-500" />
            <h2 className="text-lg font-bold text-slate-800">Previous Diagnoses</h2>
          </div>
          <div className="space-y-4">
            {patient.diagnoses && patient.diagnoses.length > 0 ? (
              patient.diagnoses.map((d) => (
                <div key={d.id} className="p-4 bg-slate-50 rounded-xl border border-slate-100">
                  <p className="text-sm font-semibold text-slate-800">{d.title}</p>
                  {d.description && <p className="text-sm text-slate-600 mt-1">{d.description}</p>}
                  {d.symptoms && <p className="text-xs text-slate-500 mt-1"><span className="font-medium">Symptoms:</span> {d.symptoms}</p>}
                  {d.recommended_tests && <p className="text-xs text-slate-500 mt-1"><span className="font-medium">Recommended tests:</span> {d.recommended_tests}</p>}
                  <p className="text-xs text-slate-400 mt-2">
                    {d.visit_date ? new Date(d.visit_date).toLocaleDateString() : (d.created_at ? new Date(d.created_at).toLocaleDateString() : "")}
                  </p>
                </div>
              ))
            ) : (
              <p className="text-sm text-slate-500">No diagnoses recorded.</p>
            )}
          </div>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="bg-white rounded-2xl shadow-sm border border-slate-100 p-6">
          <div className="flex items-center gap-3 mb-6 border-b border-slate-100 pb-4">
            <FileText className="w-5 h-5 text-amber-500" />
            <h2 className="text-lg font-bold text-slate-800">Previous Prescriptions</h2>
          </div>
          <div className="space-y-4">
            {patient.prescriptions && patient.prescriptions.length > 0 ? (
              patient.prescriptions.map((p) => (
                <div key={p.id} className="p-4 bg-slate-50 rounded-xl border border-slate-100">
                  <p className="text-sm font-semibold text-slate-800">{p.medicine_name} — {p.dosage}</p>
                  <p className="text-xs text-slate-500 mt-1">{p.frequency} · {p.duration}</p>
                  {p.instructions && <p className="text-xs text-slate-500 mt-1">{p.instructions}</p>}
                  <p className="text-xs text-slate-400 mt-2">{p.prescribed_date ? new Date(p.prescribed_date).toLocaleDateString() : ""}</p>
                </div>
              ))
            ) : (
              <p className="text-sm text-slate-500">No prescriptions recorded.</p>
            )}
          </div>
        </motion.div>
      </div>

      {/* Modals */}
      {diagnosisModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg p-6 max-h-[90vh] overflow-y-auto">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-bold">New Diagnosis</h3>
              <button onClick={() => setDiagnosisModal(false)}><X className="w-5 h-5 text-slate-500" /></button>
            </div>
            {diagnosisError && <div className="p-3 mb-4 rounded-xl bg-rose-50 border border-rose-100 text-rose-600 text-xs font-semibold">{diagnosisError}</div>}
            <form onSubmit={handleDiagnosis} className="space-y-3">
              <div>
                <label className="block text-xs font-bold text-slate-500 mb-1 uppercase tracking-wide">Title *</label>
                <input
                  required
                  type="text"
                  className="w-full border border-slate-200 rounded-xl p-2.5 text-sm focus:ring-2 focus:ring-cyan-500 outline-none"
                  placeholder="e.g. Type 2 Diabetes Mellitus"
                  value={diagnosisForm.title}
                  onChange={(e) => setDiagnosisForm({ ...diagnosisForm, title: e.target.value })}
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-500 mb-1 uppercase tracking-wide">Visit Date *</label>
                <input
                  required
                  type="date"
                  className="w-full border border-slate-200 rounded-xl p-2.5 text-sm focus:ring-2 focus:ring-cyan-500 outline-none"
                  value={diagnosisForm.visit_date}
                  onChange={(e) => setDiagnosisForm({ ...diagnosisForm, visit_date: e.target.value })}
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-500 mb-1 uppercase tracking-wide">Description</label>
                <textarea
                  className="w-full border border-slate-200 rounded-xl p-2.5 text-sm focus:ring-2 focus:ring-cyan-500 outline-none"
                  rows={2}
                  placeholder="Diagnosis summary..."
                  value={diagnosisForm.description}
                  onChange={(e) => setDiagnosisForm({ ...diagnosisForm, description: e.target.value })}
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-500 mb-1 uppercase tracking-wide">Symptoms</label>
                <textarea
                  className="w-full border border-slate-200 rounded-xl p-2.5 text-sm focus:ring-2 focus:ring-cyan-500 outline-none"
                  rows={2}
                  placeholder="Reported symptoms..."
                  value={diagnosisForm.symptoms}
                  onChange={(e) => setDiagnosisForm({ ...diagnosisForm, symptoms: e.target.value })}
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-500 mb-1 uppercase tracking-wide">Doctor Notes</label>
                <textarea
                  className="w-full border border-slate-200 rounded-xl p-2.5 text-sm focus:ring-2 focus:ring-cyan-500 outline-none"
                  rows={2}
                  placeholder="Clinical notes..."
                  value={diagnosisForm.doctor_notes}
                  onChange={(e) => setDiagnosisForm({ ...diagnosisForm, doctor_notes: e.target.value })}
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-500 mb-1 uppercase tracking-wide">Recommended Tests</label>
                <input
                  type="text"
                  className="w-full border border-slate-200 rounded-xl p-2.5 text-sm focus:ring-2 focus:ring-cyan-500 outline-none"
                  placeholder="e.g. Fasting Blood Sugar, HbA1c"
                  value={diagnosisForm.recommended_tests}
                  onChange={(e) => setDiagnosisForm({ ...diagnosisForm, recommended_tests: e.target.value })}
                />
              </div>
              <button type="submit" disabled={diagnosisSubmitting} className="w-full bg-cyan-600 text-white rounded-xl py-2.5 font-bold hover:bg-cyan-700 disabled:opacity-60">
                {diagnosisSubmitting ? "Saving..." : "Submit"}
              </button>
            </form>
          </div>
        </div>
      )}

      {prescriptionModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg p-6 max-h-[90vh] overflow-y-auto">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-bold">New Prescription</h3>
              <button onClick={() => setPrescriptionModal(false)}><X className="w-5 h-5 text-slate-500" /></button>
            </div>
            {prescriptionError && <div className="p-3 mb-4 rounded-xl bg-rose-50 border border-rose-100 text-rose-600 text-xs font-semibold">{prescriptionError}</div>}
            <form onSubmit={handlePrescription} className="space-y-3">
              <div>
                <label className="block text-xs font-bold text-slate-500 mb-1 uppercase tracking-wide">Medicine Name *</label>
                <input
                  required
                  type="text"
                  className="w-full border border-slate-200 rounded-xl p-2.5 text-sm focus:ring-2 focus:ring-emerald-500 outline-none"
                  placeholder="e.g. Metformin"
                  value={prescriptionForm.medicine_name}
                  onChange={(e) => setPrescriptionForm({ ...prescriptionForm, medicine_name: e.target.value })}
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold text-slate-500 mb-1 uppercase tracking-wide">Dosage *</label>
                  <input
                    required
                    type="text"
                    className="w-full border border-slate-200 rounded-xl p-2.5 text-sm focus:ring-2 focus:ring-emerald-500 outline-none"
                    placeholder="e.g. 500mg"
                    value={prescriptionForm.dosage}
                    onChange={(e) => setPrescriptionForm({ ...prescriptionForm, dosage: e.target.value })}
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-500 mb-1 uppercase tracking-wide">Frequency *</label>
                  <input
                    required
                    type="text"
                    className="w-full border border-slate-200 rounded-xl p-2.5 text-sm focus:ring-2 focus:ring-emerald-500 outline-none"
                    placeholder="e.g. Twice daily"
                    value={prescriptionForm.frequency}
                    onChange={(e) => setPrescriptionForm({ ...prescriptionForm, frequency: e.target.value })}
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold text-slate-500 mb-1 uppercase tracking-wide">Duration *</label>
                  <input
                    required
                    type="text"
                    className="w-full border border-slate-200 rounded-xl p-2.5 text-sm focus:ring-2 focus:ring-emerald-500 outline-none"
                    placeholder="e.g. 90 days"
                    value={prescriptionForm.duration}
                    onChange={(e) => setPrescriptionForm({ ...prescriptionForm, duration: e.target.value })}
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-500 mb-1 uppercase tracking-wide">Prescribed Date *</label>
                  <input
                    required
                    type="date"
                    className="w-full border border-slate-200 rounded-xl p-2.5 text-sm focus:ring-2 focus:ring-emerald-500 outline-none"
                    value={prescriptionForm.prescribed_date}
                    onChange={(e) => setPrescriptionForm({ ...prescriptionForm, prescribed_date: e.target.value })}
                  />
                </div>
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-500 mb-1 uppercase tracking-wide">Instructions</label>
                <textarea
                  className="w-full border border-slate-200 rounded-xl p-2.5 text-sm focus:ring-2 focus:ring-emerald-500 outline-none"
                  rows={2}
                  placeholder="e.g. Take after meals"
                  value={prescriptionForm.instructions}
                  onChange={(e) => setPrescriptionForm({ ...prescriptionForm, instructions: e.target.value })}
                />
              </div>
              <button type="submit" disabled={prescriptionSubmitting} className="w-full bg-emerald-600 text-white rounded-xl py-2.5 font-bold hover:bg-emerald-700 disabled:opacity-60">
                {prescriptionSubmitting ? "Saving..." : "Submit"}
              </button>
            </form>
          </div>
        </div>
      )}

      {labModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-bold">Request Laboratory Test</h3>
              <button onClick={() => setLabModal(false)}><X className="w-5 h-5 text-slate-500" /></button>
            </div>

            {labSuccess ? (
              <div className="text-center py-4">
                <CheckCircle className="w-12 h-12 text-emerald-500 mx-auto mb-3" />
                <p className="font-semibold text-slate-800">{labSuccess.panel} requested</p>
                <p className="text-sm text-slate-500 mt-1">Priority: {labSuccess.priority}. It now appears in the Lab Technician&apos;s pending queue.</p>
                <div className="flex gap-2 mt-5">
                  <button onClick={() => setLabSuccess(null)} className="flex-1 py-2 rounded-xl border border-slate-200 text-sm font-semibold text-slate-700 hover:bg-slate-50">
                    Request Another
                  </button>
                  <button onClick={() => setLabModal(false)} className="flex-1 py-2 rounded-xl bg-indigo-600 text-white text-sm font-semibold hover:bg-indigo-700">
                    Done
                  </button>
                </div>
              </div>
            ) : (
              <form onSubmit={handleRequestTest} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Investigation</label>
                  <select
                    required
                    value={labForm.panel_code}
                    onChange={(e) => setLabForm({ ...labForm, panel_code: e.target.value })}
                    className="w-full border border-slate-200 rounded-xl p-3 focus:ring-2 focus:ring-indigo-500 outline-none text-sm"
                  >
                    <option value="">Select an investigation…</option>
                    {labPanels.map((p) => (
                      <option key={p.code} value={p.code}>{p.name} ({p.category})</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Priority</label>
                  <select
                    value={labForm.priority}
                    onChange={(e) => setLabForm({ ...labForm, priority: e.target.value })}
                    className="w-full border border-slate-200 rounded-xl p-3 focus:ring-2 focus:ring-indigo-500 outline-none text-sm"
                  >
                    <option value="Routine">Routine</option>
                    <option value="Urgent">Urgent</option>
                    <option value="Emergency">Emergency</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Clinical Notes (Optional)</label>
                  <textarea
                    rows={3}
                    value={labForm.clinical_notes}
                    onChange={(e) => setLabForm({ ...labForm, clinical_notes: e.target.value })}
                    placeholder="Reason for the test, relevant history..."
                    className="w-full border border-slate-200 rounded-xl p-3 focus:ring-2 focus:ring-indigo-500 outline-none text-sm"
                  />
                </div>
                {labError && <p className="text-sm text-rose-600">{labError}</p>}
                <button
                  type="submit"
                  disabled={labSubmitting || !labForm.panel_code}
                  className="w-full bg-indigo-600 text-white rounded-xl py-2.5 font-bold hover:bg-indigo-700 disabled:opacity-50"
                >
                  {labSubmitting ? "Sending…" : "Send Request to Laboratory"}
                </button>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
