"use client";

import React, { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
import { KeyRound, Search, Loader2, X, Check, Clock, ShieldCheck, ShieldOff } from "lucide-react";
import { getDoctorAccessRequests, requestPatientAccess, searchDoctorPatients } from "@/lib/session";

interface AccessRequest {
  request_id: string;
  patient_id: string;
  patient_user_id?: string | null;
  patient_name?: string | null;
  requested_resource?: string | null;
  purpose?: string | null;
  status: string;
  requested_at?: string | null;
  decided_at?: string | null;
  decision_note?: string | null;
}

interface PatientHit {
  id: string;
  user_id?: string | null;
  full_name?: string | null;
  gender?: string | null;
}

const STATUS_STYLE: Record<string, string> = {
  Pending: "bg-amber-50 text-amber-700 border-amber-200",
  Authorized: "bg-emerald-50 text-emerald-700 border-emerald-200",
  Rejected: "bg-rose-50 text-rose-700 border-rose-200",
  Revoked: "bg-slate-100 text-slate-600 border-slate-200",
};

const STATUS_LABEL: Record<string, string> = {
  Pending: "Awaiting patient",
  Authorized: "Approved",
  Rejected: "Declined",
  Revoked: "Withdrawn",
};

export default function DoctorAccessRequestsPage() {
  const [requests, setRequests] = useState<AccessRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [notice, setNotice] = useState("");

  const [modal, setModal] = useState(false);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<PatientHit[]>([]);
  const [searching, setSearching] = useState(false);
  const [chosen, setChosen] = useState<PatientHit | null>(null);
  const [purpose, setPurpose] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState("");

  const load = useCallback(async () => {
    try {
      setRequests(await getDoctorAccessRequests());
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

  const runSearch = async () => {
    if (query.trim().length < 2) return;
    setSearching(true);
    setFormError("");
    try {
      const data = await searchDoctorPatients(query.trim());
      setHits(Array.isArray(data) ? data : data?.patients || []);
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Search failed");
    } finally {
      setSearching(false);
    }
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!chosen) return;
    setSubmitting(true);
    setFormError("");
    try {
      await requestPatientAccess({ patient_id: chosen.id, purpose: purpose.trim() });
      setNotice(
        `Request sent to ${chosen.full_name}. They decide whether to grant access — you will be notified either way.`
      );
      setModal(false);
      setChosen(null);
      setPurpose("");
      setQuery("");
      setHits([]);
      await load();
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Could not send the request.");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto space-y-4">
        <div className="h-8 w-64 bg-slate-200 animate-pulse rounded-md" />
        {[1, 2].map((i) => <div key={i} className="h-24 bg-slate-200 animate-pulse rounded-2xl" />)}
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col sm:flex-row sm:items-center gap-4"
      >
        <div className="flex-1">
          <h1 className="text-xl md:text-2xl font-bold text-slate-800">Access Requests</h1>
          <p className="text-slate-500 mt-1">
            Ask a patient you are not already treating for permission to read their record.
          </p>
        </div>
        <button
          onClick={() => { setModal(true); setFormError(""); }}
          className="flex items-center justify-center gap-2 px-4 py-2.5 bg-cyan-600 hover:bg-cyan-700 text-white rounded-xl text-sm font-bold transition-colors flex-shrink-0"
        >
          <KeyRound className="w-4 h-4" /> Request Access
        </button>
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
          <KeyRound className="w-14 h-14 mx-auto text-slate-300 mb-4" />
          <h3 className="text-lg font-bold text-slate-700">No Requests Yet</h3>
          <p className="text-slate-500 mt-1 max-w-md mx-auto">
            You read the records of patients you are already treating without asking.
            Use this only for a patient you have no existing relationship with.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {requests.map((r, idx) => (
            <motion.div
              key={r.request_id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.04 }}
              className="bg-white rounded-2xl shadow-sm border border-slate-100 p-5"
            >
              <div className="flex flex-col sm:flex-row sm:items-start gap-4">
                <div className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 ${
                  r.status === "Authorized" ? "bg-emerald-50 text-emerald-600"
                  : r.status === "Rejected" ? "bg-rose-50 text-rose-500"
                  : "bg-amber-50 text-amber-600"
                }`}>
                  {r.status === "Authorized" ? <ShieldCheck className="w-5 h-5" />
                    : r.status === "Rejected" ? <ShieldOff className="w-5 h-5" />
                    : <Clock className="w-5 h-5" />}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="text-base font-bold text-slate-800">
                      {r.patient_name || "Unknown patient"}
                    </h3>
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border uppercase tracking-wide ${STATUS_STYLE[r.status] || STATUS_STYLE.Revoked}`}>
                      {STATUS_LABEL[r.status] || r.status}
                    </span>
                  </div>
                  <p className="text-sm text-slate-500 mt-0.5">{r.patient_user_id || ""}</p>
                  <p className="text-sm text-slate-600 mt-2">{r.purpose}</p>
                  <p className="text-xs text-slate-400 mt-2">
                    Requested {r.requested_at ? new Date(r.requested_at).toLocaleString() : "—"}
                    {r.decided_at ? ` · decided ${new Date(r.decided_at).toLocaleString()}` : ""}
                  </p>
                  {r.decision_note && (
                    <p className="text-xs text-slate-500 mt-1.5 italic">
                      Patient note: {r.decision_note}
                    </p>
                  )}
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      )}

      {modal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg p-6 max-h-[90vh] overflow-y-auto">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-bold">Request access</h3>
              <button onClick={() => setModal(false)} aria-label="Close">
                <X className="w-5 h-5 text-slate-500" />
              </button>
            </div>

            <form onSubmit={submit} className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-slate-500 mb-1 uppercase tracking-wide">
                  Patient
                </label>
                {chosen ? (
                  <div className="flex items-center gap-3 p-3 rounded-xl bg-cyan-50 border border-cyan-100">
                    <div className="flex-1">
                      <p className="font-bold text-slate-800 text-sm">{chosen.full_name}</p>
                      <p className="text-xs text-slate-500">{chosen.user_id}</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setChosen(null)}
                      className="text-xs font-bold text-cyan-700 hover:underline"
                    >
                      Change
                    </button>
                  </div>
                ) : (
                  <>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); runSearch(); } }}
                        placeholder="Name or patient ID"
                        className="flex-1 border border-slate-200 rounded-xl px-3 py-2 text-sm focus:ring-2 focus:ring-cyan-500 outline-none"
                      />
                      <button
                        type="button"
                        onClick={runSearch}
                        disabled={searching || query.trim().length < 2}
                        className="px-3 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 disabled:opacity-50"
                        aria-label="Search"
                      >
                        {searching ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
                      </button>
                    </div>
                    {hits.length > 0 && (
                      <div className="mt-2 border border-slate-200 rounded-xl divide-y divide-slate-100 max-h-48 overflow-y-auto">
                        {hits.map((h) => (
                          <button
                            key={h.id}
                            type="button"
                            onClick={() => { setChosen(h); setHits([]); }}
                            className="w-full text-left px-3 py-2 hover:bg-slate-50"
                          >
                            <p className="text-sm font-semibold text-slate-800">{h.full_name}</p>
                            <p className="text-xs text-slate-500">{h.user_id}</p>
                          </button>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-500 mb-1 uppercase tracking-wide">
                  Clinical reason
                </label>
                <textarea
                  className="w-full border border-slate-200 rounded-xl p-2.5 text-sm focus:ring-2 focus:ring-cyan-500 outline-none"
                  rows={3}
                  required
                  minLength={15}
                  placeholder="e.g. Reviewing prior cardiac history before a scheduled procedure next week."
                  value={purpose}
                  onChange={(e) => setPurpose(e.target.value)}
                />
                {/* Stated up front rather than discovered through a 422: the patient
                    reads this to decide, so a throwaway reason is refused. */}
                <p className="text-xs text-slate-400 mt-1">
                  The patient reads this to decide. A short sentence at minimum —
                  &ldquo;urgent&rdquo; will be refused.
                </p>
              </div>

              {formError && (
                <div className="p-2.5 rounded-xl bg-rose-50 border border-rose-100 text-rose-700 text-xs font-semibold">
                  {formError}
                </div>
              )}

              <div className="flex gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => setModal(false)}
                  className="flex-1 py-2.5 rounded-xl border border-slate-200 text-sm font-bold text-slate-700 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting || !chosen || purpose.trim().length < 15}
                  className="flex-1 py-2.5 rounded-xl bg-cyan-600 hover:bg-cyan-700 text-white text-sm font-bold disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {submitting
                    ? <><Loader2 className="w-4 h-4 animate-spin" /> Sending…</>
                    : "Send Request"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
