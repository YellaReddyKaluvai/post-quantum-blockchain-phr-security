"use client";

import React, { useEffect, useState } from "react";
import { History, Loader2, CheckCircle } from "lucide-react";
import { CareTeamSuggestion, adminAssignCareTeam, getCareTeamSuggestions } from "@/lib/session";

const REASON = "Continuing care from before care teams";

/**
 * Nurses' recent patients that have no care-team assignment.
 *
 * Before care teams any nurse could open any chart, so nurses may be caring
 * for patients they can no longer reach. Their own recorded work is listed
 * here for an administrator to review; nothing is granted until it is
 * allocated, one pair at a time or all shown at once.
 */
export default function CareTeamSuggestions({ onAllocated }: { onAllocated: () => void }) {
  const [days, setDays] = useState(90);
  const [rows, setRows] = useState<CareTeamSuggestion[] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [done, setDone] = useState("");
  const [version, setVersion] = useState(0);      // bumped to reload after allocating

  useEffect(() => {
    let live = true;
    getCareTeamSuggestions(days)
      .then((r) => { if (live) { setRows(r); setError(""); } })
      .catch((e) => { if (live) setError(e instanceof Error ? e.message : "Failed to load suggestions"); });
    return () => { live = false; };
  }, [days, version]);

  const key = (s: CareTeamSuggestion) => `${s.nurse_id}:${s.patient_id}`;

  const allocate = async (list: CareTeamSuggestion[]) => {
    if (busy || list.length === 0) return;
    if (list.length > 1 && !window.confirm(`Allocate all ${list.length} nurse–patient pairs shown, for 7 days each?`)) return;
    setError("");
    setDone("");
    let made = 0;
    for (const s of list) {
      setBusy(key(s));
      try {
        await adminAssignCareTeam({ patient_id: s.patient_id, nurse_id: s.nurse_id, reason: REASON, duration_hours: 168 });
        made += 1;
      } catch (e) {
        setError(`${s.nurse_name} → ${s.patient_name}: ${e instanceof Error ? e.message : "failed"}`);
        break;
      }
    }
    setBusy(null);
    if (made) setDone(`${made} assignment${made === 1 ? "" : "s"} made for 7 days.`);
    setVersion((v) => v + 1);
    onAllocated();
  };

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-6">
      <div className="flex flex-wrap items-center gap-3 mb-2">
        <History className="w-4 h-4 text-amber-600" />
        <h2 className="text-sm font-bold text-slate-700">Recent nursing work without an assignment</h2>
        <label htmlFor="sg-days" className="ml-auto text-xs text-slate-500">Activity in the last</label>
        <select id="sg-days" value={days} onChange={(e) => setDays(Number(e.target.value))}
          className="px-2 py-1 rounded-lg border border-slate-200 text-xs bg-white">
          {[30, 90, 180, 365].map((d) => <option key={d} value={d}>{d} days</option>)}
        </select>
        <button type="button" onClick={() => allocate(rows ?? [])} disabled={!rows?.length || busy !== null}
          className="px-3 py-1.5 rounded-lg text-xs font-bold bg-amber-600 text-white hover:bg-amber-700 disabled:opacity-50">
          Allocate all shown
        </button>
      </div>
      <p className="text-xs text-slate-500 mb-4">
        From each nurse&apos;s own vitals, notes and medication rounds. Review before allocating — past work is evidence, not authorization.
      </p>
      {done && <p className="mb-3 text-sm font-semibold text-emerald-700 flex items-center gap-1"><CheckCircle className="w-4 h-4" />{done}</p>}
      {error && <p role="alert" className="mb-3 text-sm font-semibold text-rose-600">{error}</p>}
      {rows === null ? (
        <div className="h-16 rounded-xl bg-slate-50 animate-pulse" />
      ) : rows.length === 0 ? (
        <p className="text-sm text-slate-500">Every nurse&apos;s recent patients are covered by an assignment.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-400 uppercase tracking-wide">
                <th className="py-2 pr-4">Nurse</th><th className="py-2 pr-4">Patient</th>
                <th className="py-2 pr-4">Entries</th><th className="py-2 pr-4">Last activity</th><th className="py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((s) => (
                <tr key={key(s)}>
                  <td className="py-2 pr-4">{s.nurse_name}<span className="block text-[11px] text-slate-400">{s.nurse_user_id}</span></td>
                  <td className="py-2 pr-4">{s.patient_name}<span className="block text-[11px] text-slate-400">{s.patient_user_id}</span></td>
                  <td className="py-2 pr-4 text-slate-600">{s.entries}</td>
                  <td className="py-2 pr-4 text-slate-500 whitespace-nowrap">{new Date(s.last_activity).toLocaleString()}</td>
                  <td className="py-2 text-right">
                    <button type="button" onClick={() => allocate([s])} disabled={busy !== null}
                      className="px-2.5 py-1 rounded-lg text-xs font-bold text-cyan-700 hover:bg-cyan-50 disabled:opacity-50 inline-flex items-center gap-1">
                      {busy === key(s) && <Loader2 className="w-3 h-3 animate-spin" />} Allocate
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
