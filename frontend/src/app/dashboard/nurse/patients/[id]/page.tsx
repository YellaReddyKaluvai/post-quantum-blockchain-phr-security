"use client";

import React, { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { motion } from "framer-motion";
import {
  User, Activity, ClipboardList, Pill, ChevronLeft, Plus, X,
  Droplet, AlertTriangle, Check, Loader2,
} from "lucide-react";
import {
  getNursePatientDetail, recordPatientVitals, addNursingNote, administerMedication,
} from "@/lib/session";

interface VitalsRecord {
  id: string;
  temperature_celsius?: number | null;
  blood_pressure_systolic?: number | null;
  blood_pressure_diastolic?: number | null;
  heart_rate?: number | null;
  spo2?: number | null;
  respiratory_rate?: number | null;
  weight_kg?: number | null;
  height_cm?: number | null;
  notes?: string | null;
  recorded_at?: string | null;
  nurse_name?: string | null;
}

interface NursingNote {
  id: string;
  note_type: string;
  content: string;
  created_at?: string | null;
  nurse_name?: string | null;
}

interface ActivePrescription {
  id: string;
  medicine_name: string;
  dosage: string;
  frequency: string;
  duration: string;
  instructions?: string | null;
  prescribed_date?: string | null;
  last_administered_at?: string | null;
  last_administered_status?: string | null;
}

interface NursePatientDetail {
  profile: {
    id: string;
    user_id?: string;
    full_name: string;
    gender: string;
    blood_group?: string | null;
    status?: string;
  };
  vitals_history: VitalsRecord[];
  nursing_notes: NursingNote[];
  active_prescriptions: ActivePrescription[];
}

const emptyVitals = {
  temperature_celsius: "",
  blood_pressure_systolic: "",
  blood_pressure_diastolic: "",
  heart_rate: "",
  spo2: "",
  respiratory_rate: "",
  weight_kg: "",
  height_cm: "",
  notes: "",
};

// Mirrors the server-side thresholds in _vitals_out_of_range so a nurse sees
// the same judgement the alerting logic will make, at the moment of entry.
function flagVital(key: string, value: number): boolean {
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

export default function NursePatientChart() {
  const params = useParams();
  const patientId = params.id as string;

  const [data, setData] = useState<NursePatientDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  const [vitalsModal, setVitalsModal] = useState(false);
  const [noteModal, setNoteModal] = useState(false);
  const [medModal, setMedModal] = useState<ActivePrescription | null>(null);

  const [vitalsForm, setVitalsForm] = useState(emptyVitals);
  const [noteForm, setNoteForm] = useState({ note_type: "Observation", content: "" });
  const [medForm, setMedForm] = useState({ status: "Administered", remarks: "" });

  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState("");
  const [flashFlags, setFlashFlags] = useState<string[] | null>(null);

  const fetchDetail = useCallback(async () => {
    try {
      setData(await getNursePatientDetail(patientId));
      setLoadError("");
    } catch (error) {
      console.error(error);
      setLoadError(error instanceof Error ? error.message : "Could not load this patient's chart.");
    } finally {
      setLoading(false);
    }
  }, [patientId]);

  useEffect(() => { fetchDetail(); }, [fetchDetail]);

  const handleVitals = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError("");
    setSubmitting(true);
    try {
      // Only send fields the nurse actually filled in; empty strings would
      // otherwise be sent as nulls and fail the "at least one reading" rule
      // in a confusing way.
      const payload: Record<string, unknown> = {};
      Object.entries(vitalsForm).forEach(([k, v]) => {
        if (v !== "") payload[k] = k === "notes" ? v : Number(v);
      });
      const res = await recordPatientVitals(patientId, payload);
      setVitalsModal(false);
      setVitalsForm(emptyVitals);
      setFlashFlags(res.flags?.length ? res.flags : []);
      await fetchDetail();
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Failed to record vitals.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleNote = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError("");
    setSubmitting(true);
    try {
      await addNursingNote(patientId, noteForm);
      setNoteModal(false);
      setNoteForm({ note_type: "Observation", content: "" });
      await fetchDetail();
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Failed to add note.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleMedication = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!medModal) return;
    setFormError("");
    setSubmitting(true);
    try {
      await administerMedication(patientId, medModal.id, medForm);
      setMedModal(null);
      setMedForm({ status: "Administered", remarks: "" });
      await fetchDetail();
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Failed to record administration.");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return <div className="h-96 bg-slate-200 animate-pulse rounded-2xl" />;

  if (loadError) {
    return (
      <div className="max-w-3xl mx-auto space-y-4">
        <Link href="/dashboard/nurse/patients" className="flex items-center gap-2 text-slate-500 hover:text-slate-800">
          <ChevronLeft className="w-4 h-4" /> Back to Patients
        </Link>
        <div className="p-4 rounded-xl bg-rose-50 border border-rose-100 text-rose-700 text-sm font-semibold">
          {loadError}
        </div>
      </div>
    );
  }

  if (!data) return <div className="text-center p-6 text-slate-500">Patient not found.</div>;

  const { profile, vitals_history, nursing_notes, active_prescriptions } = data;
  const latest = vitals_history[0];

  const inputClass = "w-full border border-slate-200 rounded-xl p-2.5 text-sm focus:ring-2 focus:ring-cyan-500 outline-none";
  const labelClass = "block text-xs font-bold text-slate-500 mb-1 uppercase tracking-wide";

  const vitalCells: { key: string; label: string; value?: number | null; unit: string }[] = [
    { key: "temperature_celsius", label: "Temp", value: latest?.temperature_celsius, unit: "°C" },
    { key: "heart_rate", label: "Heart Rate", value: latest?.heart_rate, unit: "bpm" },
    { key: "spo2", label: "SpO₂", value: latest?.spo2, unit: "%" },
    { key: "blood_pressure_systolic", label: "BP Systolic", value: latest?.blood_pressure_systolic, unit: "mmHg" },
    { key: "blood_pressure_diastolic", label: "BP Diastolic", value: latest?.blood_pressure_diastolic, unit: "mmHg" },
    { key: "respiratory_rate", label: "Resp. Rate", value: latest?.respiratory_rate, unit: "/min" },
  ];

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <Link href="/dashboard/nurse/patients" className="flex items-center gap-2 text-slate-500 hover:text-slate-800 transition-colors">
        <ChevronLeft className="w-4 h-4" /> Back to Patients
      </Link>

      {flashFlags !== null && (
        <div className={`p-4 rounded-xl border text-sm font-semibold flex items-start gap-3 ${
          flashFlags.length
            ? "bg-amber-50 border-amber-200 text-amber-800"
            : "bg-emerald-50 border-emerald-200 text-emerald-800"
        }`}>
          {flashFlags.length ? <AlertTriangle className="w-5 h-5 flex-shrink-0 mt-0.5" /> : <Check className="w-5 h-5 flex-shrink-0 mt-0.5" />}
          <div>
            {flashFlags.length ? (
              <>
                <p>Recorded. Out-of-range: {flashFlags.join(", ")}.</p>
                <p className="font-normal mt-0.5">The attending doctor has been alerted.</p>
              </>
            ) : (
              <p>Vitals recorded. All readings within normal range.</p>
            )}
          </div>
          <button onClick={() => setFlashFlags(null)} className="ml-auto text-current/60 hover:text-current">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Patient header */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
        className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100 flex flex-col md:flex-row gap-6 items-center md:items-start">
        <div className="w-20 h-20 rounded-full bg-cyan-100 flex items-center justify-center flex-shrink-0">
          <User className="w-9 h-9 text-cyan-600" />
        </div>
        <div className="flex-1 grid grid-cols-2 md:grid-cols-4 gap-4 w-full">
          <div>
            <p className="text-xs text-slate-400 uppercase tracking-wider">Name</p>
            <p className="text-lg font-bold text-slate-800">{profile.full_name}</p>
          </div>
          <div>
            <p className="text-xs text-slate-400 uppercase tracking-wider">Patient ID</p>
            <p className="text-sm font-medium text-slate-700">{profile.user_id || "—"}</p>
          </div>
          <div>
            <p className="text-xs text-slate-400 uppercase tracking-wider">Gender</p>
            <p className="text-sm font-medium text-slate-700">{profile.gender}</p>
          </div>
          <div>
            <p className="text-xs text-slate-400 uppercase tracking-wider">Blood Group</p>
            <p className="text-sm font-medium text-slate-700 flex items-center gap-1.5">
              <Droplet className="w-3.5 h-3.5 text-rose-400" />
              {profile.blood_group || "Not recorded"}
            </p>
          </div>
        </div>
        <div className="flex flex-col gap-2 w-full md:w-auto">
          <button onClick={() => { setFormError(""); setVitalsModal(true); }}
            className="flex items-center justify-center gap-2 px-4 py-2 bg-cyan-600 hover:bg-cyan-700 text-white rounded-xl text-sm font-bold transition-colors">
            <Plus className="w-4 h-4" /> Record Vitals
          </button>
          <button onClick={() => { setFormError(""); setNoteModal(true); }}
            className="flex items-center justify-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-sm font-bold transition-colors">
            <Plus className="w-4 h-4" /> Add Note
          </button>
        </div>
      </motion.div>

      {/* Latest vitals at a glance */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}
        className="bg-white rounded-2xl shadow-sm border border-slate-100 p-6">
        <div className="flex items-center gap-3 mb-5 border-b border-slate-100 pb-4">
          <Activity className="w-5 h-5 text-cyan-500" />
          <h2 className="text-lg font-bold text-slate-800">Latest Vitals</h2>
          {latest?.recorded_at && (
            <span className="ml-auto text-xs text-slate-400">
              {new Date(latest.recorded_at).toLocaleString()} · {latest.nurse_name}
            </span>
          )}
        </div>
        {!latest ? (
          <p className="text-sm text-slate-500">No vitals recorded yet.</p>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            {vitalCells.map((c) => {
              const has = c.value !== null && c.value !== undefined;
              const abnormal = has && flagVital(c.key, Number(c.value));
              return (
                <div key={c.key}
                  className={`p-3 rounded-xl border ${abnormal ? "bg-amber-50 border-amber-200" : "bg-slate-50 border-slate-100"}`}>
                  <p className="text-[10px] uppercase font-bold text-slate-400 tracking-wide">{c.label}</p>
                  <p className={`text-lg font-bold tabular-nums ${abnormal ? "text-amber-700" : "text-slate-800"}`}>
                    {has ? c.value : "—"}
                    {has && <span className="text-xs font-medium ml-0.5">{c.unit}</span>}
                  </p>
                  {abnormal && <p className="text-[10px] font-bold text-amber-600 mt-0.5">Out of range</p>}
                </div>
              );
            })}
          </div>
        )}
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Medication rounds */}
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
          className="bg-white rounded-2xl shadow-sm border border-slate-100 p-6">
          <div className="flex items-center gap-3 mb-5 border-b border-slate-100 pb-4">
            <Pill className="w-5 h-5 text-blue-500" />
            <h2 className="text-lg font-bold text-slate-800">Medication Rounds</h2>
          </div>
          <div className="space-y-3">
            {active_prescriptions.length === 0 ? (
              <p className="text-sm text-slate-500">No prescriptions on file.</p>
            ) : active_prescriptions.map((p) => (
              <div key={p.id} className="p-4 bg-slate-50 rounded-xl border border-slate-100">
                <div className="flex justify-between items-start gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-bold text-slate-800">{p.medicine_name} — {p.dosage}</p>
                    <p className="text-xs text-slate-500 mt-0.5">{p.frequency} · {p.duration}</p>
                    {p.instructions && <p className="text-xs text-slate-500 mt-0.5">{p.instructions}</p>}
                    <p className="text-[11px] text-slate-400 mt-1.5">
                      {p.last_administered_at
                        ? `Last: ${p.last_administered_status} · ${new Date(p.last_administered_at).toLocaleString()}`
                        : "Not yet administered"}
                    </p>
                  </div>
                  <button onClick={() => { setFormError(""); setMedModal(p); }}
                    className="flex-shrink-0 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-bold transition-colors">
                    Record
                  </button>
                </div>
              </div>
            ))}
          </div>
        </motion.div>

        {/* Nursing notes */}
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}
          className="bg-white rounded-2xl shadow-sm border border-slate-100 p-6">
          <div className="flex items-center gap-3 mb-5 border-b border-slate-100 pb-4">
            <ClipboardList className="w-5 h-5 text-emerald-500" />
            <h2 className="text-lg font-bold text-slate-800">Nursing Notes</h2>
          </div>
          <div className="space-y-3">
            {nursing_notes.length === 0 ? (
              <p className="text-sm text-slate-500">No notes recorded.</p>
            ) : nursing_notes.map((n) => (
              <div key={n.id} className="p-4 bg-slate-50 rounded-xl border border-slate-100">
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
        </motion.div>
      </div>

      {/* Vitals history */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}
        className="bg-white rounded-2xl shadow-sm border border-slate-100 p-6">
        <div className="flex items-center gap-3 mb-5 border-b border-slate-100 pb-4">
          <Activity className="w-5 h-5 text-slate-400" />
          <h2 className="text-lg font-bold text-slate-800">Vitals History</h2>
        </div>
        {vitals_history.length === 0 ? (
          <p className="text-sm text-slate-500">No history yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[640px]">
              <thead>
                <tr className="text-left text-[10px] uppercase tracking-wide text-slate-400 border-b border-slate-100">
                  <th className="py-2 pr-4 font-bold">Recorded</th>
                  <th className="py-2 pr-4 font-bold">Temp</th>
                  <th className="py-2 pr-4 font-bold">HR</th>
                  <th className="py-2 pr-4 font-bold">SpO₂</th>
                  <th className="py-2 pr-4 font-bold">BP</th>
                  <th className="py-2 pr-4 font-bold">Resp</th>
                  <th className="py-2 font-bold">By</th>
                </tr>
              </thead>
              <tbody className="tabular-nums">
                {vitals_history.map((v) => (
                  <tr key={v.id} className="border-b border-slate-50 last:border-0">
                    <td className="py-2.5 pr-4 text-slate-600 whitespace-nowrap">
                      {v.recorded_at ? new Date(v.recorded_at).toLocaleString() : "—"}
                    </td>
                    <td className="py-2.5 pr-4 text-slate-800">{v.temperature_celsius ?? "—"}</td>
                    <td className="py-2.5 pr-4 text-slate-800">{v.heart_rate ?? "—"}</td>
                    <td className="py-2.5 pr-4 text-slate-800">{v.spo2 ?? "—"}</td>
                    <td className="py-2.5 pr-4 text-slate-800">
                      {v.blood_pressure_systolic && v.blood_pressure_diastolic
                        ? `${v.blood_pressure_systolic}/${v.blood_pressure_diastolic}` : "—"}
                    </td>
                    <td className="py-2.5 pr-4 text-slate-800">{v.respiratory_rate ?? "—"}</td>
                    <td className="py-2.5 text-slate-500">{v.nurse_name || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </motion.div>

      {/* ── Record Vitals ── */}
      {vitalsModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg p-6 max-h-[90vh] overflow-y-auto">
            <div className="flex justify-between items-center mb-1">
              <h3 className="text-lg font-bold">Record Vitals</h3>
              <button onClick={() => setVitalsModal(false)}><X className="w-5 h-5 text-slate-500" /></button>
            </div>
            <p className="text-xs text-slate-500 mb-4">Fill in whatever you measured — at least one reading is required.</p>
            {formError && <div className="p-3 mb-4 rounded-xl bg-rose-50 border border-rose-100 text-rose-600 text-xs font-semibold">{formError}</div>}
            <form onSubmit={handleVitals} className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className={labelClass}>Temperature (°C)</label>
                  <input type="number" step="0.1" className={inputClass} placeholder="36.8"
                    value={vitalsForm.temperature_celsius}
                    onChange={(e) => setVitalsForm({ ...vitalsForm, temperature_celsius: e.target.value })} />
                </div>
                <div>
                  <label className={labelClass}>Heart Rate (bpm)</label>
                  <input type="number" className={inputClass} placeholder="72"
                    value={vitalsForm.heart_rate}
                    onChange={(e) => setVitalsForm({ ...vitalsForm, heart_rate: e.target.value })} />
                </div>
                <div>
                  <label className={labelClass}>BP Systolic</label>
                  <input type="number" className={inputClass} placeholder="120"
                    value={vitalsForm.blood_pressure_systolic}
                    onChange={(e) => setVitalsForm({ ...vitalsForm, blood_pressure_systolic: e.target.value })} />
                </div>
                <div>
                  <label className={labelClass}>BP Diastolic</label>
                  <input type="number" className={inputClass} placeholder="80"
                    value={vitalsForm.blood_pressure_diastolic}
                    onChange={(e) => setVitalsForm({ ...vitalsForm, blood_pressure_diastolic: e.target.value })} />
                </div>
                <div>
                  <label className={labelClass}>SpO₂ (%)</label>
                  <input type="number" className={inputClass} placeholder="98"
                    value={vitalsForm.spo2}
                    onChange={(e) => setVitalsForm({ ...vitalsForm, spo2: e.target.value })} />
                </div>
                <div>
                  <label className={labelClass}>Resp. Rate (/min)</label>
                  <input type="number" className={inputClass} placeholder="16"
                    value={vitalsForm.respiratory_rate}
                    onChange={(e) => setVitalsForm({ ...vitalsForm, respiratory_rate: e.target.value })} />
                </div>
                <div>
                  <label className={labelClass}>Weight (kg)</label>
                  <input type="number" step="0.1" className={inputClass} placeholder="70"
                    value={vitalsForm.weight_kg}
                    onChange={(e) => setVitalsForm({ ...vitalsForm, weight_kg: e.target.value })} />
                </div>
                <div>
                  <label className={labelClass}>Height (cm)</label>
                  <input type="number" step="0.1" className={inputClass} placeholder="170"
                    value={vitalsForm.height_cm}
                    onChange={(e) => setVitalsForm({ ...vitalsForm, height_cm: e.target.value })} />
                </div>
              </div>
              <div>
                <label className={labelClass}>Notes</label>
                <textarea className={inputClass} rows={2} placeholder="Anything worth flagging..."
                  value={vitalsForm.notes}
                  onChange={(e) => setVitalsForm({ ...vitalsForm, notes: e.target.value })} />
              </div>
              <button type="submit" disabled={submitting}
                className="w-full bg-cyan-600 text-white rounded-xl py-2.5 font-bold hover:bg-cyan-700 disabled:opacity-60 flex items-center justify-center gap-2">
                {submitting ? <><Loader2 className="w-4 h-4 animate-spin" /> Saving…</> : "Record Vitals"}
              </button>
            </form>
          </div>
        </div>
      )}

      {/* ── Add Note ── */}
      {noteModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-bold">Add Nursing Note</h3>
              <button onClick={() => setNoteModal(false)}><X className="w-5 h-5 text-slate-500" /></button>
            </div>
            {formError && <div className="p-3 mb-4 rounded-xl bg-rose-50 border border-rose-100 text-rose-600 text-xs font-semibold">{formError}</div>}
            <form onSubmit={handleNote} className="space-y-3">
              <div>
                <label className={labelClass}>Type</label>
                <select className={inputClass} value={noteForm.note_type}
                  onChange={(e) => setNoteForm({ ...noteForm, note_type: e.target.value })}>
                  <option value="Observation">Observation</option>
                  <option value="Care">Care</option>
                  <option value="Incident">Incident</option>
                </select>
              </div>
              <div>
                <label className={labelClass}>Note *</label>
                <textarea required className={inputClass} rows={4} placeholder="What did you observe or do?"
                  value={noteForm.content}
                  onChange={(e) => setNoteForm({ ...noteForm, content: e.target.value })} />
              </div>
              <button type="submit" disabled={submitting}
                className="w-full bg-emerald-600 text-white rounded-xl py-2.5 font-bold hover:bg-emerald-700 disabled:opacity-60 flex items-center justify-center gap-2">
                {submitting ? <><Loader2 className="w-4 h-4 animate-spin" /> Saving…</> : "Add Note"}
              </button>
            </form>
          </div>
        </div>
      )}

      {/* ── Record Administration ── */}
      {medModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6">
            <div className="flex justify-between items-center mb-1">
              <h3 className="text-lg font-bold">Record Administration</h3>
              <button onClick={() => setMedModal(null)}><X className="w-5 h-5 text-slate-500" /></button>
            </div>
            <p className="text-sm text-slate-600 mb-4">
              {medModal.medicine_name} — {medModal.dosage} · {medModal.frequency}
            </p>
            {formError && <div className="p-3 mb-4 rounded-xl bg-rose-50 border border-rose-100 text-rose-600 text-xs font-semibold">{formError}</div>}
            <form onSubmit={handleMedication} className="space-y-3">
              <div>
                <label className={labelClass}>Outcome</label>
                <select className={inputClass} value={medForm.status}
                  onChange={(e) => setMedForm({ ...medForm, status: e.target.value })}>
                  <option value="Administered">Administered</option>
                  <option value="Refused">Refused by patient</option>
                  <option value="Held">Held</option>
                  <option value="Missed">Missed</option>
                </select>
              </div>
              <div>
                <label className={labelClass}>Remarks</label>
                <textarea className={inputClass} rows={3} placeholder="Reaction, reason for holding, etc."
                  value={medForm.remarks}
                  onChange={(e) => setMedForm({ ...medForm, remarks: e.target.value })} />
              </div>
              <button type="submit" disabled={submitting}
                className="w-full bg-blue-600 text-white rounded-xl py-2.5 font-bold hover:bg-blue-700 disabled:opacity-60 flex items-center justify-center gap-2">
                {submitting ? <><Loader2 className="w-4 h-4 animate-spin" /> Saving…</> : "Record"}
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
