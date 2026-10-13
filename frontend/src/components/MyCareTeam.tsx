"use client";

import React, { useEffect, useState } from "react";
import { HeartHandshake, Clock } from "lucide-react";
import { CareTeamMember, getMyCareTeam } from "@/lib/session";

/** The nurses who can currently open this patient's chart, and on whose say-so. */
export default function MyCareTeam() {
  const [team, setTeam] = useState<CareTeamMember[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getMyCareTeam().then(setTeam).catch((e) => setError(e instanceof Error ? e.message : "Failed to load"));
  }, []);

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-5">
      <div className="flex items-center gap-2 mb-1">
        <HeartHandshake className="w-5 h-5 text-cyan-600" />
        <h2 className="text-base font-bold text-slate-800">Nursing care team</h2>
      </div>
      <p className="text-xs text-slate-500 mb-3">
        Nurses can read your chart and record vitals only while assigned to you. A nurse added by a
        doctor loses access as soon as you withdraw that doctor.
      </p>
      {error ? (
        <p className="text-sm text-rose-600">{error}</p>
      ) : team === null ? (
        <div className="h-10 rounded-xl bg-slate-50 animate-pulse" />
      ) : team.length === 0 ? (
        <p className="text-sm text-slate-500">No nurses are assigned to you.</p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {team.map((m) => (
            <li key={m.id} className="py-2.5">
              <p className="text-sm font-semibold text-slate-800">{m.nurse_name}</p>
              <p className="text-xs text-slate-500">
                {m.reason} · added by {m.assigned_by_role === "Administrator" ? "hospital administration" : m.assigned_by_name}
              </p>
              <p className="text-[11px] text-slate-400 flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {m.expires_at ? `Until ${new Date(m.expires_at).toLocaleString()}` : "No end date"}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
