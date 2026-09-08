"use client";

import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Pill, Check, X, PauseCircle, AlertTriangle } from "lucide-react";
import { getOwnAdherence } from "@/lib/session";

interface Round {
  id: string;
  medicine_name?: string | null;
  dosage?: string | null;
  frequency?: string | null;
  status: string;
  remarks?: string | null;
  nurse_name?: string | null;
  prescriber_name?: string | null;
  administered_at?: string | null;
}

interface Summary {
  total_rounds: number;
  administered: number;
  refused: number;
  held: number;
  missed: number;
  adherence_percent: number | null;
  needs_attention: boolean;
}

const STATUS: Record<string, { tint: string; icon: React.ElementType; label: string }> = {
  Administered: { tint: "text-emerald-700 bg-emerald-50 border-emerald-200", icon: Check, label: "Given" },
  Refused:      { tint: "text-rose-700 bg-rose-50 border-rose-200",          icon: X,     label: "Refused" },
  Held:         { tint: "text-amber-700 bg-amber-50 border-amber-200",       icon: PauseCircle, label: "Held" },
  Missed:       { tint: "text-slate-700 bg-slate-100 border-slate-200",      icon: AlertTriangle, label: "Missed" },
};

export default function MedicationHistoryPage() {
  const [rounds, setRounds] = useState<Round[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    getOwnAdherence()
      .then((d) => { setRounds(d.rounds || []); setSummary(d.summary || null); })
      .catch((error) => {
        console.error(error);
        setLoadError("Could not load your medication history. Check that the backend is running.");
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto space-y-4">
        <div className="h-8 w-56 bg-slate-200 animate-pulse rounded-md" />
        <div className="h-24 bg-slate-200 animate-pulse rounded-2xl" />
        <div className="h-64 bg-slate-200 animate-pulse rounded-2xl" />
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-xl md:text-2xl font-bold text-slate-800">Medication History</h1>
        <p className="text-slate-500 mt-1">
          Every dose recorded by nursing staff — given, refused, held or missed.
        </p>
      </motion.div>

      {loadError && (
        <div className="p-3 rounded-xl bg-rose-50 border border-rose-100 text-rose-700 text-sm font-semibold">
          {loadError}
        </div>
      )}

      {summary && summary.total_rounds > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: "Given", value: summary.administered, tint: "text-emerald-600 bg-emerald-50" },
            { label: "Refused", value: summary.refused, tint: "text-rose-600 bg-rose-50" },
            { label: "Held", value: summary.held, tint: "text-amber-600 bg-amber-50" },
            { label: "Missed", value: summary.missed, tint: "text-slate-600 bg-slate-100" },
          ].map((s) => (
            <div key={s.label} className="bg-white rounded-2xl shadow-sm border border-slate-100 p-4">
              <p className="text-2xl font-bold text-slate-800 tabular-nums">{s.value}</p>
              <p className={`text-xs font-semibold px-2 py-0.5 rounded inline-block mt-1 ${s.tint}`}>
                {s.label}
              </p>
            </div>
          ))}
        </div>
      )}

      {summary?.needs_attention && (
        // Said plainly and without alarm. A refused or missed dose is exactly
        // what the care team needs to know about, and hiding it behind a
        // percentage would defeat the point of recording it.
        <div className="p-3.5 rounded-xl bg-amber-50 border border-amber-100 text-amber-800 text-sm flex items-start gap-2.5">
          <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <span>
            Some doses were refused or missed. Your care team can see this too — please
            raise any difficulty taking a medicine with them directly.
          </span>
        </div>
      )}

      {rounds.length === 0 && !loadError ? (
        <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-12 text-center">
          <Pill className="w-14 h-14 mx-auto text-slate-300 mb-4" />
          <h3 className="text-lg font-bold text-slate-700">No Doses Recorded</h3>
          <p className="text-slate-500 mt-1">
            Medication rounds appear here once nursing staff record one.
          </p>
        </div>
      ) : (
        <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-5">
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[560px]">
              <thead>
                <tr className="text-left text-[10px] uppercase tracking-wide text-slate-400 border-b border-slate-100">
                  <th className="py-2 pr-4 font-bold">When</th>
                  <th className="py-2 pr-4 font-bold">Medicine</th>
                  <th className="py-2 pr-4 font-bold">Outcome</th>
                  <th className="py-2 font-bold">Recorded by</th>
                </tr>
              </thead>
              <tbody>
                {rounds.map((r) => {
                  const s = STATUS[r.status] || STATUS.Missed;
                  const Icon = s.icon;
                  return (
                    <tr key={r.id} className="border-b border-slate-50 last:border-0">
                      <td className="py-2.5 pr-4 text-slate-600 whitespace-nowrap">
                        {r.administered_at ? new Date(r.administered_at).toLocaleString() : "—"}
                      </td>
                      <td className="py-2.5 pr-4">
                        <span className="font-semibold text-slate-800">{r.medicine_name || "—"}</span>
                        {r.dosage && <span className="text-slate-500"> · {r.dosage}</span>}
                      </td>
                      <td className="py-2.5 pr-4">
                        <span className={`inline-flex items-center gap-1.5 text-[11px] font-bold px-2 py-0.5 rounded-full border ${s.tint}`}>
                          <Icon className="w-3 h-3" /> {s.label}
                        </span>
                        {r.remarks && (
                          <span className="block text-xs text-slate-400 mt-0.5">{r.remarks}</span>
                        )}
                      </td>
                      <td className="py-2.5 text-slate-500">{r.nurse_name || "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
