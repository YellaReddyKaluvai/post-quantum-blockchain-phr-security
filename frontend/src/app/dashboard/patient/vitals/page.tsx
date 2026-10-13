"use client";

import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Activity, HeartPulse, Wind, Thermometer, Gauge, Scale } from "lucide-react";
import { getPatientVitals } from "@/lib/session";

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

// The same thresholds the clinical staff see, so a patient is never shown a
// reassuring reading their nurse considered abnormal.
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

export default function PatientVitalsPage() {
  const [vitals, setVitals] = useState<VitalsRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    getPatientVitals()
      .then(setVitals)
      .catch((error) => {
        console.error(error);
        setVitals([]);
        setLoadError("Could not load your vitals. Check that the backend is running.");
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="max-w-5xl mx-auto space-y-6">
        <div className="h-8 w-48 bg-slate-200 animate-pulse rounded-md" />
        <div className="h-40 bg-slate-200 animate-pulse rounded-2xl" />
      </div>
    );
  }

  const latest = vitals[0];

  const cards = [
    { key: "temperature_celsius", label: "Temperature", value: latest?.temperature_celsius, unit: "°C", icon: Thermometer, tint: "text-rose-500 bg-rose-50" },
    { key: "heart_rate", label: "Heart Rate", value: latest?.heart_rate, unit: "bpm", icon: HeartPulse, tint: "text-red-500 bg-red-50" },
    { key: "spo2", label: "Oxygen (SpO₂)", value: latest?.spo2, unit: "%", icon: Wind, tint: "text-sky-500 bg-sky-50" },
    { key: "blood_pressure_systolic", label: "BP Systolic", value: latest?.blood_pressure_systolic, unit: "mmHg", icon: Gauge, tint: "text-violet-500 bg-violet-50" },
    { key: "blood_pressure_diastolic", label: "BP Diastolic", value: latest?.blood_pressure_diastolic, unit: "mmHg", icon: Gauge, tint: "text-violet-500 bg-violet-50" },
    { key: "respiratory_rate", label: "Breathing Rate", value: latest?.respiratory_rate, unit: "/min", icon: Activity, tint: "text-teal-500 bg-teal-50" },
  ];

  const anyAbnormal = cards.some(
    (c) => c.value !== null && c.value !== undefined && isAbnormal(c.key, Number(c.value))
  );

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-xl md:text-2xl font-bold text-slate-800">My Vitals</h1>
        <p className="text-slate-500 mt-1">Measurements recorded by nursing staff during your care.</p>
      </motion.div>

      {loadError && (
        <div className="p-3 rounded-xl bg-rose-50 border border-rose-100 text-rose-700 text-sm font-semibold">
          {loadError}
        </div>
      )}

      {!loadError && vitals.length === 0 ? (
        <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-12 text-center">
          <Activity className="w-14 h-14 mx-auto text-slate-300 mb-4" />
          <h3 className="text-lg font-bold text-slate-700">No Vitals Recorded</h3>
          <p className="text-slate-500 mt-1">
            Your readings will appear here once nursing staff record them.
          </p>
        </div>
      ) : vitals.length > 0 ? (
        <>
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="bg-white rounded-2xl shadow-sm border border-slate-100 p-6"
          >
            <div className="flex items-center gap-3 mb-5 border-b border-slate-100 pb-4 flex-wrap">
              <h2 className="text-lg font-bold text-slate-800">Most Recent</h2>
              {latest?.recorded_at && (
                <span className="ml-auto text-xs text-slate-400">
                  {new Date(latest.recorded_at).toLocaleString()}
                  {latest.nurse_name ? ` · recorded by ${latest.nurse_name}` : ""}
                </span>
              )}
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
              {cards.map((c) => {
                const has = c.value !== null && c.value !== undefined;
                const abnormal = has && isAbnormal(c.key, Number(c.value));
                return (
                  <div
                    key={c.key}
                    className={`p-3 rounded-xl border ${abnormal ? "bg-amber-50 border-amber-200" : "bg-slate-50 border-slate-100"}`}
                  >
                    <div className={`w-7 h-7 rounded-lg flex items-center justify-center mb-2 ${abnormal ? "text-amber-600 bg-amber-100" : c.tint}`}>
                      <c.icon className="w-4 h-4" />
                    </div>
                    <p className="text-[10px] uppercase font-bold text-slate-400 tracking-wide">{c.label}</p>
                    <p className={`text-lg font-bold tabular-nums ${abnormal ? "text-amber-700" : "text-slate-800"}`}>
                      {has ? c.value : "—"}
                      {has && <span className="text-xs font-medium ml-0.5">{c.unit}</span>}
                    </p>
                  </div>
                );
              })}
            </div>

            {(latest?.weight_kg || latest?.height_cm) && (
              <div className="flex gap-6 mt-4 pt-4 border-t border-slate-100 text-sm text-slate-600">
                {latest.weight_kg && (
                  <span className="flex items-center gap-1.5">
                    <Scale className="w-4 h-4 text-slate-400" /> Weight: <b className="text-slate-800">{latest.weight_kg} kg</b>
                  </span>
                )}
                {latest.height_cm && (
                  <span className="flex items-center gap-1.5">
                    Height: <b className="text-slate-800">{latest.height_cm} cm</b>
                  </span>
                )}
              </div>
            )}

            {anyAbnormal && (
              // Stated plainly and without alarm: the patient should know the
              // reading was flagged, and that a clinician already has it.
              <p className="mt-4 text-xs text-amber-700 bg-amber-50 border border-amber-100 rounded-xl p-3">
                Highlighted readings fall outside the usual range. Your care team was notified
                automatically and will follow up — please raise any concerns with them directly.
              </p>
            )}
          </motion.div>

          {vitals.length > 1 && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 }}
              className="bg-white rounded-2xl shadow-sm border border-slate-100 p-6"
            >
              <h2 className="text-lg font-bold text-slate-800 mb-4 pb-4 border-b border-slate-100">History</h2>
              <div className="overflow-x-auto">
                <table className="w-full text-sm min-w-[620px]">
                  <thead>
                    <tr className="text-left text-[10px] uppercase tracking-wide text-slate-400 border-b border-slate-100">
                      <th className="py-2 pr-4 font-bold">Recorded</th>
                      <th className="py-2 pr-4 font-bold">Temp</th>
                      <th className="py-2 pr-4 font-bold">Heart Rate</th>
                      <th className="py-2 pr-4 font-bold">SpO₂</th>
                      <th className="py-2 pr-4 font-bold">Blood Pressure</th>
                      <th className="py-2 font-bold">Recorded By</th>
                    </tr>
                  </thead>
                  <tbody className="tabular-nums">
                    {vitals.map((v) => (
                      <tr key={v.id} className="border-b border-slate-50 last:border-0">
                        <td className="py-2.5 pr-4 text-slate-600 whitespace-nowrap">
                          {v.recorded_at ? new Date(v.recorded_at).toLocaleString() : "—"}
                        </td>
                        <td className="py-2.5 pr-4 text-slate-800">{v.temperature_celsius ?? "—"}</td>
                        <td className="py-2.5 pr-4 text-slate-800">{v.heart_rate ?? "—"}</td>
                        <td className="py-2.5 pr-4 text-slate-800">{v.spo2 ?? "—"}</td>
                        <td className="py-2.5 pr-4 text-slate-800">
                          {v.blood_pressure_systolic && v.blood_pressure_diastolic
                            ? `${v.blood_pressure_systolic}/${v.blood_pressure_diastolic}`
                            : "—"}
                        </td>
                        <td className="py-2.5 text-slate-500">{v.nurse_name || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </motion.div>
          )}
        </>
      ) : null}
    </div>
  );
}
