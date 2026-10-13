"use client";

import React, { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Users, UserPlus, Loader2, Search, CheckCircle, Clock } from "lucide-react";
import { CareTeamMember, adminAssignCareTeam, adminEndCareTeam, getAdminCareTeams } from "@/lib/session";
import CareTeamSuggestions from "@/components/CareTeamSuggestions";

const DURATIONS = [
  { hours: 24, label: "24 hours" },
  { hours: 72, label: "3 days" },
  { hours: 168, label: "7 days" },
  { hours: 336, label: "14 days" },
  { hours: 720, label: "30 days" },
];

const emptyForm = { patient_id: "", nurse_id: "", reason: "", duration_hours: 168 };

/**
 * Ward allocation: which nurses may open which patients' charts.
 *
 * Doctors delegate access from the patient's chart; administrators allocate
 * nurses to patients here. Either way the patient is notified, and every
 * assignment is time-boxed and ended rather than deleted.
 */
export default function AdminCareTeamsPage() {
  const [rows, setRows] = useState<CareTeamMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [query, setQuery] = useState("");

  const [form, setForm] = useState(emptyForm);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState("");
  const [success, setSuccess] = useState("");
  const [ending, setEnding] = useState<string | null>(null);

  const load = useCallback(async (q: string) => {
    try {
      setRows(await getAdminCareTeams(q));
      setLoadError("");
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "Could not load care teams.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const t = setTimeout(() => load(query.trim()), 250);
    return () => clearTimeout(t);
  }, [query, load]);

  const reasonOk = form.reason.trim().length >= 10 && form.reason.trim().split(/\s+/).length >= 2;
  const canSubmit = form.patient_id.trim() && form.nurse_id.trim() && reasonOk && !submitting;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) {
      setFormError("Enter a patient ID, a nurse ID and the reason for the allocation.");
      return;
    }
    setSubmitting(true);
    setFormError("");
    setSuccess("");
    try {
      const added = await adminAssignCareTeam({
        patient_id: form.patient_id.trim(), nurse_id: form.nurse_id.trim(),
        reason: form.reason.trim(), duration_hours: form.duration_hours,
      });
      setSuccess(`${added.nurse_name} is now on ${added.patient_name}'s care team.`);
      setForm(emptyForm);
      await load(query.trim());
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed to assign the nurse.");
    } finally {
      setSubmitting(false);
    }
  };

  const end = async (m: CareTeamMember) => {
    if (ending) return;
    if (!window.confirm(`End ${m.nurse_name}'s access to ${m.patient_name}'s chart now?`)) return;
    setEnding(m.id);
    setSuccess("");
    try {
      await adminEndCareTeam(m.id);
      setSuccess(`${m.nurse_name} was removed from ${m.patient_name}'s care team.`);
      await load(query.trim());
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Failed to end the assignment.");
    } finally {
      setEnding(null);
    }
  };

  const input = "w-full px-3 py-2 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-200";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800 flex items-center gap-2">
          <Users className="w-6 h-6 text-cyan-600" /> Care Teams
        </h1>
        <p className="text-sm text-slate-500">
          Nurses can open only the charts of patients they are assigned to. Allocate ward nurses here;
          treating doctors add nurses from the patient&apos;s chart.
        </p>
      </div>

      <motion.form onSubmit={submit} noValidate initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
        className="bg-white rounded-2xl shadow-sm border border-slate-100 p-6 grid grid-cols-1 md:grid-cols-2 gap-4">
        <h2 className="md:col-span-2 text-sm font-bold text-slate-700 flex items-center gap-2">
          <UserPlus className="w-4 h-4" /> Allocate a nurse
        </h2>
        <div>
          <label htmlFor="ct-patient" className="block text-xs font-bold text-slate-500 mb-1">Patient ID</label>
          <input id="ct-patient" className={input} placeholder="PAT-2026-000001" value={form.patient_id}
            onChange={(e) => setForm((f) => ({ ...f, patient_id: e.target.value }))} />
        </div>
        <div>
          <label htmlFor="ct-nurse" className="block text-xs font-bold text-slate-500 mb-1">Nurse ID</label>
          <input id="ct-nurse" className={input} placeholder="NUR-2026-000001" value={form.nurse_id}
            onChange={(e) => setForm((f) => ({ ...f, nurse_id: e.target.value }))} />
        </div>
        <div>
          <label htmlFor="ct-reason" className="block text-xs font-bold text-slate-500 mb-1">Reason</label>
          <input id="ct-reason" className={input} maxLength={300} placeholder="e.g. Ward 4B night shift"
            value={form.reason} onChange={(e) => setForm((f) => ({ ...f, reason: e.target.value }))} />
        </div>
        <div>
          <label htmlFor="ct-duration" className="block text-xs font-bold text-slate-500 mb-1">Access for</label>
          <select id="ct-duration" className={`${input} bg-white`} value={form.duration_hours}
            onChange={(e) => setForm((f) => ({ ...f, duration_hours: Number(e.target.value) }))}>
            {DURATIONS.map((d) => <option key={d.hours} value={d.hours}>{d.label}</option>)}
          </select>
        </div>
        <div className="md:col-span-2 flex items-center gap-3">
          {formError && <p className="text-sm font-semibold text-rose-600" role="alert">{formError}</p>}
          {success && <p className="text-sm font-semibold text-emerald-700 flex items-center gap-1"><CheckCircle className="w-4 h-4" />{success}</p>}
          <button type="submit" disabled={!canSubmit}
            className="ml-auto px-4 py-2 rounded-xl text-sm font-bold bg-cyan-600 text-white hover:bg-cyan-700 disabled:opacity-50 flex items-center gap-2">
            {submitting && <Loader2 className="w-4 h-4 animate-spin" />} Allocate
          </button>
        </div>
      </motion.form>

      <CareTeamSuggestions onAllocated={() => load(query.trim())} />

      <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-6">
        <div className="flex items-center gap-3 mb-4">
          <h2 className="text-sm font-bold text-slate-700">Active assignments</h2>
          <div className="relative ml-auto w-full max-w-xs">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input aria-label="Filter assignments" className={`${input} pl-9`} placeholder="Filter by patient or nurse"
              value={query} onChange={(e) => setQuery(e.target.value)} />
          </div>
        </div>
        {loading ? (
          <div className="h-24 rounded-xl bg-slate-50 animate-pulse" />
        ) : loadError ? (
          <p className="text-sm text-rose-600">{loadError}</p>
        ) : rows.length === 0 ? (
          <p className="text-sm text-slate-500">No active care-team assignments{query ? " match this filter" : ""}.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-slate-400 uppercase tracking-wide">
                  <th className="py-2 pr-4">Patient</th><th className="py-2 pr-4">Nurse</th>
                  <th className="py-2 pr-4">Reason</th><th className="py-2 pr-4">Added by</th>
                  <th className="py-2 pr-4">Until</th><th className="py-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((m) => (
                  <tr key={m.id}>
                    <td className="py-2 pr-4">{m.patient_name}<span className="block text-[11px] text-slate-400">{m.patient_user_id}</span></td>
                    <td className="py-2 pr-4">{m.nurse_name}<span className="block text-[11px] text-slate-400">{m.nurse_user_id}</span></td>
                    <td className="py-2 pr-4 text-slate-600 max-w-xs truncate">{m.reason}</td>
                    <td className="py-2 pr-4 text-slate-600">{m.assigned_by_role === "Administrator" ? "Administration" : m.assigned_by_name}</td>
                    <td className="py-2 pr-4 text-slate-500 whitespace-nowrap">
                      <Clock className="w-3 h-3 inline mr-1" />{m.expires_at ? new Date(m.expires_at).toLocaleString() : "No end date"}
                    </td>
                    <td className="py-2 text-right">
                      <button type="button" onClick={() => end(m)} disabled={ending === m.id}
                        className="px-2.5 py-1 rounded-lg text-xs font-bold text-rose-600 hover:bg-rose-50 disabled:opacity-50 inline-flex items-center gap-1">
                        {ending === m.id && <Loader2 className="w-3 h-3 animate-spin" />} End
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
