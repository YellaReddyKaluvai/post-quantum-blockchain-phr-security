"use client";

import React, { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
import {
  ShieldQuestion, Stethoscope, Check, X, Loader2, Clock, ShieldCheck, ShieldOff,
} from "lucide-react";
import { getPatientAccessRequests, decideAccessRequest } from "@/lib/session";

interface AccessRequest {
  request_id: string;
  doctor_id: string;
  doctor_user_id?: string | null;
  doctor_name?: string | null;
  specialization?: string | null;
  requested_resource?: string | null;
  purpose?: string | null;
  status: string;
  requested_at?: string | null;
  decided_at?: string | null;
  decision_note?: string | null;
}

const STATUS_STYLE: Record<string, string> = {
  Pending: "bg-amber-50 text-amber-700 border-amber-200",
  Authorized: "bg-emerald-50 text-emerald-700 border-emerald-200",
  Rejected: "bg-rose-50 text-rose-700 border-rose-200",
  Revoked: "bg-slate-100 text-slate-600 border-slate-200",
};

const STATUS_LABEL: Record<string, string> = {
  Pending: "Awaiting your decision",
  Authorized: "You approved this",
  Rejected: "You declined this",
  Revoked: "Access withdrawn",
};

export default function PatientAccessRequestsPage() {
  const [requests, setRequests] = useState<AccessRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [deciding, setDeciding] = useState<{ req: AccessRequest; approve: boolean } | null>(null);
  const [note, setNote] = useState("");

  const load = useCallback(async () => {
    try {
      setRequests(await getPatientAccessRequests());
      setLoadError("");
    } catch (error) {
      console.error(error);
      setRequests([]);
      setLoadError("Could not load your access requests. Check that the backend is running.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const confirm = async () => {
    if (!deciding) return;
    setBusy(deciding.req.request_id);
    try {
      await decideAccessRequest(
        deciding.req.request_id,
        deciding.approve ? "approve" : "reject",
        note || undefined
      );
      setNotice(
        deciding.approve
          ? `Dr. ${deciding.req.doctor_name} can now read your record. You can withdraw this at any time from Record Access.`
          : `Dr. ${deciding.req.doctor_name} was declined and cannot read your record.`
      );
      setDeciding(null);
      setNote("");
      await load();
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "Could not record your decision.");
    } finally {
      setBusy(null);
    }
  };

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto space-y-4">
        <div className="h-8 w-64 bg-slate-200 animate-pulse rounded-md" />
        {[1, 2].map((i) => <div key={i} className="h-32 bg-slate-200 animate-pulse rounded-2xl" />)}
      </div>
    );
  }

  const pending = requests.filter((r) => r.status === "Pending");
  const decided = requests.filter((r) => r.status !== "Pending");

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-xl md:text-2xl font-bold text-slate-800">Access Requests</h1>
        <p className="text-slate-500 mt-1">
          Doctors who are not already treating you must ask before reading your record.
          Nothing is shared until you decide.
        </p>
      </motion.div>

      {notice && (
        <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-100 text-emerald-800 text-sm font-semibold flex items-start gap-2.5">
          <Check className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <span>{notice}</span>
          <button onClick={() => setNotice("")} className="ml-auto opacity-60 hover:opacity-100" aria-label="Dismiss">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {loadError && (
        <div className="p-3 rounded-xl bg-rose-50 border border-rose-100 text-rose-700 text-sm font-semibold">
          {loadError}
        </div>
      )}

      {requests.length === 0 && !loadError ? (
        <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-12 text-center">
          <ShieldQuestion className="w-14 h-14 mx-auto text-slate-300 mb-4" />
          <h3 className="text-lg font-bold text-slate-700">No Requests</h3>
          <p className="text-slate-500 mt-1 max-w-md mx-auto">
            When a doctor who is not already treating you asks to read your record,
            it will appear here for you to approve or decline.
          </p>
        </div>
      ) : (
        <>
          {pending.length > 0 && (
            <section className="space-y-3">
              <h2 className="text-sm font-bold text-slate-500 uppercase tracking-wide">
                Waiting for you ({pending.length})
              </h2>
              {pending.map((r, idx) => (
                <motion.div
                  key={r.request_id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: idx * 0.05 }}
                  className="bg-white rounded-2xl shadow-sm border-2 border-amber-200 p-5"
                >
                  <div className="flex flex-col sm:flex-row sm:items-start gap-4">
                    <div className="w-11 h-11 rounded-full bg-amber-50 text-amber-600 flex items-center justify-center flex-shrink-0">
                      <Stethoscope className="w-5 h-5" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="text-base font-bold text-slate-800">
                          Dr. {r.doctor_name || "Unknown"}
                        </h3>
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border uppercase tracking-wide ${STATUS_STYLE[r.status]}`}>
                          {STATUS_LABEL[r.status] || r.status}
                        </span>
                      </div>
                      <p className="text-sm text-slate-500 mt-0.5">
                        {r.specialization || "General"}
                        {r.doctor_user_id ? ` · ${r.doctor_user_id}` : ""}
                      </p>

                      {/* The purpose is the whole basis for the decision, so it is
                          given real weight rather than tucked into a caption. */}
                      <div className="mt-3 p-3 rounded-xl bg-slate-50 border border-slate-100">
                        <p className="text-[10px] uppercase font-bold text-slate-400 tracking-wide mb-1">
                          Why they are asking
                        </p>
                        <p className="text-sm text-slate-700">{r.purpose}</p>
                      </div>

                      <p className="text-xs text-slate-400 mt-2 flex items-center gap-1.5">
                        <Clock className="w-3.5 h-3.5" />
                        Requested {r.requested_at ? new Date(r.requested_at).toLocaleString() : "—"}
                        {r.requested_resource ? ` · ${r.requested_resource}` : ""}
                      </p>

                      <div className="flex gap-2 mt-4">
                        <button
                          onClick={() => { setDeciding({ req: r, approve: true }); setNote(""); }}
                          disabled={busy === r.request_id}
                          className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-sm font-bold transition-colors disabled:opacity-60"
                        >
                          <ShieldCheck className="w-4 h-4" /> Approve
                        </button>
                        <button
                          onClick={() => { setDeciding({ req: r, approve: false }); setNote(""); }}
                          disabled={busy === r.request_id}
                          className="flex items-center gap-2 px-4 py-2 bg-white border border-rose-200 text-rose-600 hover:bg-rose-50 rounded-xl text-sm font-bold transition-colors disabled:opacity-60"
                        >
                          <ShieldOff className="w-4 h-4" /> Decline
                        </button>
                      </div>
                    </div>
                  </div>
                </motion.div>
              ))}
            </section>
          )}

          {decided.length > 0 && (
            <section className="space-y-3">
              <h2 className="text-sm font-bold text-slate-500 uppercase tracking-wide">
                Already decided
              </h2>
              {decided.map((r) => (
                <div
                  key={r.request_id}
                  className="bg-white rounded-2xl shadow-sm border border-slate-100 p-4 flex items-center gap-4"
                >
                  <div className="w-9 h-9 rounded-full bg-slate-50 text-slate-400 flex items-center justify-center flex-shrink-0">
                    <Stethoscope className="w-4 h-4" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-bold text-slate-800 text-sm truncate">
                      Dr. {r.doctor_name || "Unknown"}
                      <span className="font-normal text-slate-400"> · {r.specialization || "General"}</span>
                    </p>
                    <p className="text-xs text-slate-400 truncate">{r.purpose}</p>
                  </div>
                  <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border uppercase tracking-wide flex-shrink-0 ${STATUS_STYLE[r.status] || STATUS_STYLE.Revoked}`}>
                    {STATUS_LABEL[r.status] || r.status}
                  </span>
                </div>
              ))}
            </section>
          )}
        </>
      )}

      <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200 text-sm text-slate-600">
        <p className="font-bold text-slate-700 mb-1">What approving does</p>
        <p>
          The doctor gains read access to your medical record. You can withdraw it again
          at any time from <strong>Record Access</strong>, and your decision is recorded
          permanently so it can be audited. In a genuine emergency a clinician can still
          override a withdrawal — if that happens you are notified immediately and the
          override is logged.
        </p>
      </div>

      {deciding && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6">
            <div className="flex justify-between items-center mb-1">
              <h3 className="text-lg font-bold">
                {deciding.approve ? "Approve this request?" : "Decline this request?"}
              </h3>
              <button onClick={() => setDeciding(null)} aria-label="Close">
                <X className="w-5 h-5 text-slate-500" />
              </button>
            </div>
            <p className="text-sm text-slate-600 mb-4">
              {deciding.approve
                ? `Dr. ${deciding.req.doctor_name} will be able to read your medical record. They will be notified.`
                : `Dr. ${deciding.req.doctor_name} will not be able to read your record. They will be notified.`}
            </p>
            <label className="block text-xs font-bold text-slate-500 mb-1 uppercase tracking-wide">
              Note (optional)
            </label>
            <textarea
              className="w-full border border-slate-200 rounded-xl p-2.5 text-sm focus:ring-2 focus:ring-cyan-500 outline-none"
              rows={3}
              placeholder="Only you and an administrator can see this."
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
            <div className="flex gap-2 mt-4">
              <button
                onClick={() => setDeciding(null)}
                className="flex-1 py-2.5 rounded-xl border border-slate-200 text-sm font-bold text-slate-700 hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                onClick={confirm}
                disabled={busy === deciding.req.request_id}
                className={`flex-1 py-2.5 rounded-xl text-white text-sm font-bold disabled:opacity-60 flex items-center justify-center gap-2 ${
                  deciding.approve
                    ? "bg-emerald-600 hover:bg-emerald-700"
                    : "bg-rose-600 hover:bg-rose-700"
                }`}
              >
                {busy === deciding.req.request_id
                  ? <><Loader2 className="w-4 h-4 animate-spin" /> Saving…</>
                  : deciding.approve ? "Approve" : "Decline"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
