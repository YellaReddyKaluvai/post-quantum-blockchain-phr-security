"use client";

import React, { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
import {
  ShieldCheck, ShieldOff, Stethoscope, AlertTriangle, Loader2, X, Check,
} from "lucide-react";
import { getPatientConsent, revokePatientConsent, grantPatientConsent } from "@/lib/session";

interface ConsentEntry {
  doctor_id: string;
  doctor_user_id?: string | null;
  doctor_name: string;
  specialization?: string | null;
  relationship: string;
  status: string;
  revoked_at?: string | null;
  emergency_override_until?: string | null;
}

export default function PatientConsentPage() {
  const [entries, setEntries] = useState<ConsentEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<ConsentEntry | null>(null);
  const [reason, setReason] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    try {
      setEntries(await getPatientConsent());
      setLoadError("");
    } catch (error) {
      console.error(error);
      setEntries([]);
      setLoadError("Could not load your access list. Check that the backend is running.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleRevoke = async () => {
    if (!confirming) return;
    setBusy(confirming.doctor_id);
    try {
      const res = await revokePatientConsent(confirming.doctor_id, reason || undefined);
      setNotice(res.message);
      setConfirming(null);
      setReason("");
      await load();
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "Failed to withdraw access.");
    } finally {
      setBusy(null);
    }
  };

  const handleGrant = async (entry: ConsentEntry) => {
    setBusy(entry.doctor_id);
    try {
      const res = await grantPatientConsent(entry.doctor_id);
      setNotice(res.message);
      await load();
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "Failed to restore access.");
    } finally {
      setBusy(null);
    }
  };

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto space-y-4">
        <div className="h-8 w-56 bg-slate-200 animate-pulse rounded-md" />
        {[1, 2].map((i) => <div key={i} className="h-24 bg-slate-200 animate-pulse rounded-2xl" />)}
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-xl md:text-2xl font-bold text-slate-800">Record Access</h1>
        <p className="text-slate-500 mt-1">
          Clinicians who can read your records, and why. You can withdraw access at any time.
        </p>
      </motion.div>

      {notice && (
        <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-100 text-emerald-800 text-sm font-semibold flex items-start gap-2.5">
          <Check className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <span>{notice}</span>
          <button onClick={() => setNotice("")} className="ml-auto opacity-60 hover:opacity-100">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {loadError && (
        <div className="p-3 rounded-xl bg-rose-50 border border-rose-100 text-rose-700 text-sm font-semibold">
          {loadError}
        </div>
      )}

      {entries.length === 0 && !loadError ? (
        <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-12 text-center">
          <ShieldCheck className="w-14 h-14 mx-auto text-slate-300 mb-4" />
          <h3 className="text-lg font-bold text-slate-700">No Clinicians Yet</h3>
          <p className="text-slate-500 mt-1">
            Doctors appear here once they treat you — after an appointment, diagnosis or test.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {entries.map((e, idx) => {
            const revoked = e.status === "Revoked";
            const override = e.emergency_override_until
              && new Date(e.emergency_override_until) > new Date();
            return (
              <motion.div
                key={e.doctor_id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: idx * 0.05 }}
                className={`bg-white rounded-2xl shadow-sm border p-5 ${revoked ? "border-rose-100" : "border-slate-100"}`}
              >
                <div className="flex flex-col sm:flex-row sm:items-center gap-4">
                  <div className={`w-11 h-11 rounded-full flex items-center justify-center flex-shrink-0 ${revoked ? "bg-rose-50 text-rose-500" : "bg-cyan-50 text-cyan-600"}`}>
                    <Stethoscope className="w-5 h-5" />
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="text-base font-bold text-slate-800">Dr. {e.doctor_name}</h3>
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border uppercase tracking-wide ${
                        revoked
                          ? "bg-rose-50 text-rose-700 border-rose-200"
                          : "bg-emerald-50 text-emerald-700 border-emerald-200"
                      }`}>
                        {revoked ? "Access withdrawn" : "Can access"}
                      </span>
                    </div>
                    <p className="text-sm text-slate-500 mt-0.5">
                      {e.specialization || "General"}
                      {e.doctor_user_id ? ` · ${e.doctor_user_id}` : ""}
                    </p>
                    <p className="text-xs text-slate-400 mt-1">{e.relationship}</p>
                  </div>

                  <div className="flex-shrink-0">
                    {revoked ? (
                      <button
                        onClick={() => handleGrant(e)}
                        disabled={busy === e.doctor_id}
                        className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-sm font-bold transition-colors disabled:opacity-60"
                      >
                        {busy === e.doctor_id
                          ? <><Loader2 className="w-4 h-4 animate-spin" /> Restoring…</>
                          : <><ShieldCheck className="w-4 h-4" /> Restore Access</>}
                      </button>
                    ) : (
                      <button
                        onClick={() => { setConfirming(e); setReason(""); }}
                        disabled={busy === e.doctor_id}
                        className="flex items-center gap-2 px-4 py-2 bg-white border border-rose-200 text-rose-600 hover:bg-rose-50 rounded-xl text-sm font-bold transition-colors disabled:opacity-60"
                      >
                        <ShieldOff className="w-4 h-4" /> Withdraw Access
                      </button>
                    )}
                  </div>
                </div>

                {override && (
                  // Break-glass in force: the patient must see this plainly,
                  // not discover it in an audit log later.
                  <div className="mt-3 p-3 rounded-xl bg-amber-50 border border-amber-100 text-amber-800 text-xs font-semibold flex items-start gap-2">
                    <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-px" />
                    <span>
                      This clinician declared <strong>emergency access</strong>, which overrides your
                      withdrawal until {new Date(e.emergency_override_until!).toLocaleString()}.
                      It is permanently recorded and reviewable by an administrator.
                    </span>
                  </div>
                )}
              </motion.div>
            );
          })}
        </div>
      )}

      <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200 text-sm text-slate-600">
        <p className="font-bold text-slate-700 mb-1">What withdrawing does</p>
        <p>
          The clinician immediately stops being able to open your reports and records.
          Care they already provided — past diagnoses, prescriptions and notes — stays in your
          medical record, because a record of treatment given cannot be unwritten. In a genuine
          emergency a clinician can still override this; if that happens you are notified at once
          and the override is permanently logged.
        </p>
      </div>

      {confirming && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6">
            <div className="flex justify-between items-center mb-1">
              <h3 className="text-lg font-bold">Withdraw access?</h3>
              <button onClick={() => setConfirming(null)}><X className="w-5 h-5 text-slate-500" /></button>
            </div>
            <p className="text-sm text-slate-600 mb-4">
              Dr. {confirming.doctor_name} will no longer be able to open your records.
              They will be notified.
            </p>
            <label className="block text-xs font-bold text-slate-500 mb-1 uppercase tracking-wide">
              Reason (optional)
            </label>
            <textarea
              className="w-full border border-slate-200 rounded-xl p-2.5 text-sm focus:ring-2 focus:ring-rose-500 outline-none"
              rows={3}
              placeholder="Only you and an administrator can see this."
              value={reason}
              onChange={(ev) => setReason(ev.target.value)}
            />
            <div className="flex gap-2 mt-4">
              <button
                onClick={() => setConfirming(null)}
                className="flex-1 py-2.5 rounded-xl border border-slate-200 text-sm font-bold text-slate-700 hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                onClick={handleRevoke}
                disabled={busy === confirming.doctor_id}
                className="flex-1 py-2.5 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-sm font-bold disabled:opacity-60 flex items-center justify-center gap-2"
              >
                {busy === confirming.doctor_id
                  ? <><Loader2 className="w-4 h-4 animate-spin" /> Withdrawing…</>
                  : "Withdraw Access"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
