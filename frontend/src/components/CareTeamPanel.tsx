"use client";

import React, { useCallback, useEffect, useState } from "react";
import { Users, UserPlus, Loader2, X, CheckCircle, Clock } from "lucide-react";
import {
  CareTeamMember, assignCareTeamNurse, endCareTeamAssignment, getPatientCareTeam, searchNurses,
} from "@/lib/session";

const DURATIONS = [
  { hours: 12, label: "12 hours" },
  { hours: 24, label: "24 hours" },
  { hours: 72, label: "3 days" },
  { hours: 168, label: "7 days" },
];

/**
 * The nurses who may open this patient's chart.
 *
 * A nurse's access is delegated by the treating doctor and ends with the
 * doctor's own access — so this panel lives on the doctor's view of the
 * patient, and only works while that doctor is authorized for them.
 */
export default function CareTeamPanel({ patientId }: { patientId: string }) {
  const [team, setTeam] = useState<CareTeamMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [nurses, setNurses] = useState<{ id: string; user_id: string; full_name: string }[]>([]);
  const [form, setForm] = useState({ nurse_id: "", reason: "", duration_hours: 72 });
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState("");
  const [success, setSuccess] = useState("");
  const [ending, setEnding] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setTeam(await getPatientCareTeam(patientId));
      setLoadError("");
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "Failed to load the care team");
    } finally {
      setLoading(false);
    }
  }, [patientId]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => {
      searchNurses(query.trim()).then(setNurses).catch(() => setNurses([]));
    }, 250);
    return () => clearTimeout(t);
  }, [open, query]);

  const reasonTooShort = form.reason.trim().length < 10 || form.reason.trim().split(/\s+/).length < 2;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (submitting) return;
    if (!form.nurse_id) { setFormError("Choose a nurse."); return; }
    if (reasonTooShort) { setFormError("Give the clinical reason — a short phrase at least."); return; }
    setSubmitting(true);
    setFormError("");
    try {
      const added = await assignCareTeamNurse(patientId, {
        nurse_id: form.nurse_id, reason: form.reason.trim(), duration_hours: form.duration_hours,
      });
      setSuccess(`${added.nurse_name ?? "The nurse"} can now open this chart.`);
      setForm({ nurse_id: "", reason: "", duration_hours: 72 });
      setQuery("");
      setOpen(false);
      await load();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed to add the nurse");
    } finally {
      setSubmitting(false);
    }
  };

  const end = async (member: CareTeamMember) => {
    if (ending) return;
    if (!window.confirm(`Remove ${member.nurse_name ?? "this nurse"} from the care team? Their access ends now.`)) return;
    setEnding(member.id);
    try {
      await endCareTeamAssignment(patientId, member.id);
      setSuccess(`${member.nurse_name ?? "The nurse"} was removed from the care team.`);
      await load();
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Failed to remove the nurse");
    } finally {
      setEnding(null);
    }
  };

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-6">
      <div className="flex items-center gap-3 mb-4 border-b border-slate-100 pb-4">
        <Users className="w-5 h-5 text-cyan-600" />
        <div>
          <h2 className="text-lg font-bold text-slate-800">Care Team</h2>
          <p className="text-xs text-slate-500">Nurses who can open this chart. Their access ends with yours.</p>
        </div>
        <button type="button" onClick={() => { setOpen((o) => !o); setFormError(""); setSuccess(""); }}
          className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold bg-cyan-600 text-white hover:bg-cyan-700">
          {open ? <X className="w-3.5 h-3.5" /> : <UserPlus className="w-3.5 h-3.5" />}
          {open ? "Cancel" : "Add nurse"}
        </button>
      </div>

      {success && (
        <p className="mb-3 flex items-center gap-2 text-sm font-semibold text-emerald-700">
          <CheckCircle className="w-4 h-4" /> {success}
        </p>
      )}

      {open && (
        <form onSubmit={submit} className="mb-5 p-4 rounded-xl bg-slate-50 border border-slate-100 space-y-3" noValidate>
          <div>
            <label htmlFor="ct-search" className="block text-xs font-bold text-slate-500 mb-1">Nurse</label>
            <input id="ct-search" type="search" value={query} onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by name or staff ID"
              className="w-full px-3 py-2 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-200" />
            <select aria-label="Select nurse" value={form.nurse_id}
              onChange={(e) => setForm((f) => ({ ...f, nurse_id: e.target.value }))}
              className="mt-2 w-full px-3 py-2 rounded-lg border border-slate-200 text-sm bg-white">
              <option value="">{nurses.length ? "Select a nurse…" : "No approved nurses match"}</option>
              {nurses.map((n) => (
                <option key={n.id} value={n.id}>{n.full_name} ({n.user_id})</option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="ct-reason" className="block text-xs font-bold text-slate-500 mb-1">Clinical reason</label>
            <input id="ct-reason" value={form.reason} maxLength={300}
              onChange={(e) => setForm((f) => ({ ...f, reason: e.target.value }))}
              placeholder="e.g. Post-operative observations overnight"
              className="w-full px-3 py-2 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-200" />
            <p className="mt-1 text-[11px] text-slate-400">The patient is told who was added and why.</p>
          </div>
          <div>
            <label htmlFor="ct-duration" className="block text-xs font-bold text-slate-500 mb-1">Access for</label>
            <select id="ct-duration" value={form.duration_hours}
              onChange={(e) => setForm((f) => ({ ...f, duration_hours: Number(e.target.value) }))}
              className="w-full px-3 py-2 rounded-lg border border-slate-200 text-sm bg-white">
              {DURATIONS.map((d) => <option key={d.hours} value={d.hours}>{d.label}</option>)}
            </select>
          </div>
          {formError && <p className="text-sm font-semibold text-rose-600" role="alert">{formError}</p>}
          <div className="flex justify-end">
            <button type="submit" disabled={submitting || !form.nurse_id || reasonTooShort}
              className="px-4 py-2 rounded-lg text-sm font-bold bg-cyan-600 text-white hover:bg-cyan-700 disabled:opacity-50 flex items-center gap-2">
              {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
              Add to care team
            </button>
          </div>
        </form>
      )}

      {loading ? (
        <div className="h-12 rounded-xl bg-slate-50 animate-pulse" />
      ) : loadError ? (
        <p className="text-sm text-rose-600">{loadError}</p>
      ) : team.length === 0 ? (
        <p className="text-sm text-slate-500">No nurses on this patient&apos;s care team. Nurses cannot open the chart until one is added.</p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {team.map((m) => (
            <li key={m.id} className="py-3 flex items-start gap-3">
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-slate-800">
                  {m.nurse_name} <span className="text-xs font-normal text-slate-400">{m.nurse_user_id}</span>
                </p>
                <p className="text-xs text-slate-500 truncate">{m.reason}</p>
                <p className="text-[11px] text-slate-400 flex items-center gap-1 mt-0.5">
                  <Clock className="w-3 h-3" />
                  {m.expires_at ? `Until ${new Date(m.expires_at).toLocaleString()}` : "No end date"}
                  {" · "}added by {m.assigned_by_role === "Administrator" ? "administration" : m.assigned_by_name ?? "a doctor"}
                </p>
              </div>
              <button type="button" onClick={() => end(m)} disabled={ending === m.id}
                className="px-2.5 py-1 rounded-lg text-xs font-bold text-rose-600 hover:bg-rose-50 disabled:opacity-50 flex items-center gap-1">
                {ending === m.id && <Loader2 className="w-3 h-3 animate-spin" />}
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
