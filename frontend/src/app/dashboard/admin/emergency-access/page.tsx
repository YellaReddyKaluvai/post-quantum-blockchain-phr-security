"use client";

import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { ShieldAlert, Clock, User, Link2, CheckCircle2 } from "lucide-react";
import { getAdminEmergencyAccess } from "@/lib/session";

interface EmergencyRecord {
  id: string;
  patient_id: string;
  patient_name?: string | null;
  patient_user_id?: string | null;
  requester_id: string;
  requester_name?: string | null;
  requester_user_id?: string | null;
  reason: string;
  status: string;
  blockchain_tx_hash?: string | null;
  created_at?: string | null;
  expires_at?: string | null;
  is_active: boolean;
}

export default function AdminEmergencyAccessPage() {
  const [records, setRecords] = useState<EmergencyRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    getAdminEmergencyAccess()
      .then(setRecords)
      .catch((error) => {
        console.error(error);
        setRecords([]);
        setLoadError("Could not load the emergency access log. Check that the backend is running.");
      })
      .finally(() => setLoading(false));
  }, []);

  const active = records.filter((r) => r.is_active).length;

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-8 w-64 bg-slate-200 animate-pulse rounded-md" />
        {[1, 2].map((i) => <div key={i} className="h-32 bg-slate-200 animate-pulse rounded-2xl" />)}
      </div>
    );
  }

  return (
    <>
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
        <div className="flex items-center gap-3 mb-1">
          <ShieldAlert className="w-7 h-7 text-rose-500" />
          <h2 className="text-2xl sm:text-3xl font-extrabold text-slate-800">Emergency Access</h2>
        </div>
        <p className="text-sm text-slate-500">
          Break-glass declarations that overrode a patient&apos;s consent settings.
        </p>
      </motion.div>

      {loadError && (
        <div className="mb-6 p-3 rounded-xl bg-rose-50 border border-rose-100 text-rose-700 text-sm font-semibold">
          {loadError}
        </div>
      )}

      {/* Emergency access is not blocked at the point of use, so review is the
          control that makes it accountable. Say that plainly. */}
      <div className="mb-6 p-4 rounded-2xl bg-slate-50 border border-slate-200 text-sm text-slate-600">
        <p className="font-bold text-slate-700 mb-1">Why this page exists</p>
        <p>
          A clinician can override a patient&apos;s withdrawal of consent without prior approval —
          waiting for a second party in an emergency would defeat the purpose. The control is
          therefore accountability, not prevention: each declaration is time-boxed, the patient is
          notified immediately, and the record is anchored on-chain so it cannot be quietly removed.
          Reviewing these is what makes the override safe to offer.
        </p>
      </div>

      {records.length === 0 && !loadError ? (
        <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-12 text-center">
          <CheckCircle2 className="w-14 h-14 mx-auto text-emerald-300 mb-4" />
          <h3 className="text-lg font-bold text-slate-700">No Emergency Access Declared</h3>
          <p className="text-slate-500 mt-1">No clinician has overridden a consent setting.</p>
        </div>
      ) : (
        <>
          {active > 0 && (
            <div className="mb-4 p-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 text-sm font-bold flex items-center gap-2">
              <ShieldAlert className="w-4 h-4" />
              {active} declaration{active > 1 ? "s are" : " is"} still active — those records are
              accessible right now.
            </div>
          )}

          <div className="space-y-3">
            {records.map((r, idx) => (
              <motion.div
                key={r.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: idx * 0.04 }}
                className={`bg-white rounded-2xl shadow-sm border p-5 ${
                  r.is_active ? "border-amber-200 ring-1 ring-amber-100" : "border-slate-100"
                }`}
              >
                <div className="flex items-start justify-between gap-4 mb-3 flex-wrap">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={`text-[10px] font-bold px-2.5 py-1 rounded-full uppercase tracking-wide ${
                      r.is_active ? "bg-amber-100 text-amber-800" : "bg-slate-100 text-slate-600"
                    }`}>
                      {r.is_active ? "Active now" : "Expired"}
                    </span>
                    <span className="text-xs text-slate-400 flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      {r.created_at ? new Date(r.created_at).toLocaleString() : "—"}
                      {r.expires_at && ` → ${new Date(r.expires_at).toLocaleString()}`}
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
                  <div className="flex items-center gap-2 text-sm">
                    <User className="w-4 h-4 text-slate-400 flex-shrink-0" />
                    <span className="text-slate-500">Clinician:</span>
                    <span className="font-semibold text-slate-800 truncate">
                      Dr. {r.requester_name}
                      {r.requester_user_id && <span className="text-slate-400 font-normal"> ({r.requester_user_id})</span>}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 text-sm">
                    <User className="w-4 h-4 text-slate-400 flex-shrink-0" />
                    <span className="text-slate-500">Patient:</span>
                    <span className="font-semibold text-slate-800 truncate">
                      {r.patient_name}
                      {r.patient_user_id && <span className="text-slate-400 font-normal"> ({r.patient_user_id})</span>}
                    </span>
                  </div>
                </div>

                <div className="p-3 rounded-xl bg-slate-50 border border-slate-100">
                  <p className="text-[10px] uppercase font-bold text-slate-400 tracking-wide mb-1">
                    Stated reason
                  </p>
                  <p className="text-sm text-slate-700">{r.reason}</p>
                </div>

                {r.blockchain_tx_hash && (
                  <p className="text-[11px] font-mono text-slate-400 break-all mt-2 flex items-start gap-1.5">
                    <Link2 className="w-3 h-3 flex-shrink-0 mt-0.5" />
                    {r.blockchain_tx_hash}
                  </p>
                )}
              </motion.div>
            ))}
          </div>
        </>
      )}
    </>
  );
}
