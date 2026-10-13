"use client";

import React, { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
import {
  Brain, AlertTriangle, FileWarning, Network, Play, Loader2, Check, X, ShieldAlert,
  SlidersHorizontal, ShieldCheck,
} from "lucide-react";
import {
  runSecurityAnalysis, getRiskAssessments, getSecurityAlerts,
  acknowledgeAlert, getSecurityIncidents, getFederatedStatus, runFederatedRound,
  updateSecurityIncident, getSecurityPolicy, IncidentVerdict,
} from "@/lib/session";
import FederatedLearningPanel from "@/components/FederatedLearningPanel";

interface Attribution {
  feature: string;
  label: string;
  observed: number;
  peer_median?: number;
  deviations?: number;
  weight?: number;
  contribution: number;
  source?: string;        // "FEDERATED_CLASSIFIER" when the trained classifier drove the score
}

interface Assessment {
  id: string;
  actor_name?: string | null;
  actor_public_id?: string | null;
  actor_role?: string | null;
  risk_score: number;
  risk_level: string;
  detection_source: string;
  explanation: Attribution[];
  narrative: string;
  created_at?: string | null;
}

interface Alert {
  id: string;
  severity: string;
  title: string;
  summary: string;
  response: string;
  source?: string;
  actor_name?: string | null;
  actor_public_id?: string | null;
  acknowledged: boolean;
  created_at?: string | null;
}

interface Incident {
  id: string;
  incident_ref: string;
  event_type: string;
  affected_resource?: string | null;
  risk_level: string;
  detection_source: string;
  explanation?: string | null;
  response?: string | null;
  status: string;
  resolution?: string | null;
  resolved_by?: string | null;
  actor_name?: string | null;
  actor_public_id?: string | null;
  created_at?: string | null;
  closed_at?: string | null;
}

interface FederatedNode { name: string; simulated: boolean; samples: number; }
interface Federated {
  rounds_completed: number;
  latest_round?: number | null;
  aggregation: string;
  nodes: FederatedNode[];
  status: string;
  disclosure: string;
  real_nodes?: number;
  simulated_nodes?: number;
  detection_baseline?: string;
  latest_round_adopted?: boolean | null;
  latest_round_evaluation?: { adopt: boolean; reasons: string[] } | null;
  open_round?: number;
  pending_peer_submissions?: number;
  participant?: {
    configured: boolean;
    hub_url?: string | null;
    node_name?: string | null;
    last_pulled?: { hub_round: number; real_nodes: number; pulled_at: string } | null;
  };
}

interface Policy {
  risk_policy: { MEDIUM: string; HIGH: string; EMERGENCY_HIGH: string; step_up_minutes: number;
                 min_peers: number; thresholds: { MEDIUM: number; HIGH: number } };
  emergency_max_per_day: number;
  scheduled_analysis_minutes: number;
  consent_ledger: string;
}

const SOURCE_LABEL: Record<string, string> = {
  LOCAL_ANOMALY: "Anomaly detection",
  FEDERATED_IDS: "Federated IDS",
  RISK_GATE: "Risk gate (at access)",
  INTEGRITY_CHECK: "Integrity check",
  SIGNATURE_CHECK: "Signature check",
  CONSENT_LEDGER: "Consent ledger",
  ACCESS_CONTROL: "Access control",
  EMERGENCY_ACCESS: "Emergency access",
};

const LEVEL_STYLE: Record<string, string> = {
  HIGH: "bg-rose-50 text-rose-700 border-rose-200",
  MEDIUM: "bg-amber-50 text-amber-700 border-amber-200",
  LOW: "bg-emerald-50 text-emerald-700 border-emerald-200",
};

const RESPONSE_HINT: Record<string, string> = {
  MONITOR: "No action needed — recorded for context.",
  VERIFY: "Worth a look. Confirm the activity was legitimate.",
  ESCALATE: "Investigate now. An incident record was opened.",
  RESTRICT: "The operation was refused under the configured policy.",
};

export default function AiSecurityPage() {
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [federated, setFederated] = useState<Federated | null>(null);
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [closing, setClosing] = useState<string | null>(null);
  const [resolution, setResolution] = useState("");
  const [verdict, setVerdict] = useState<IncidentVerdict | "">("");
  const [incidentBusy, setIncidentBusy] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [fedRunning, setFedRunning] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<string>("");

  const load = useCallback(async (level?: string) => {
    try {
      const [a, al, inc, fed] = await Promise.all([
        getRiskAssessments(level || undefined),
        getSecurityAlerts(),
        getSecurityIncidents(),
        getFederatedStatus(),
      ]);
      setAssessments(a.assessments || []);
      setAlerts(al.alerts || []);
      setIncidents(inc.incidents || []);
      setFederated(fed);
      setError("");
      // The policy panel is informative; its absence must not hide the rest.
      getSecurityPolicy().then(setPolicy).catch(() => setPolicy(null));
    } catch (e) {
      console.error(e);
      setError("Could not load the security layer. Check that the backend is running.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(filter); }, [load, filter]);

  const analyze = async () => {
    setRunning(true);
    setError("");
    try {
      const r = await runSecurityAnalysis(720);
      const b = r.risk_breakdown || {};
      setNotice(
        `Analysed ${r.analysed} actors across ${(r.peer_groups || []).length} peer groups — ` +
        `${b.HIGH || 0} high, ${b.MEDIUM || 0} medium, ${b.LOW || 0} low.`
      );
      await load(filter);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Analysis failed.");
    } finally {
      setRunning(false);
    }
  };

  const federate = async () => {
    setFedRunning(true);
    setError("");
    try {
      const r = await runFederatedRound();
      setNotice(`Round ${r.round} complete — ${r.contributing_nodes} nodes, ${r.total_samples} samples aggregated with ${r.aggregation}.`);
      await load(filter);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Federated round failed.");
    } finally {
      setFedRunning(false);
    }
  };

  const advanceIncident = async (i: Incident, status: "Investigating" | "Closed") => {
    setIncidentBusy(i.id);
    setError("");
    try {
      await updateSecurityIncident(i.id, status, status === "Closed" ? resolution : undefined,
                                   status === "Closed" && verdict ? verdict : undefined);
      setClosing(null);
      setResolution("");
      setVerdict("");
      await load(filter);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not update that incident.");
    } finally {
      setIncidentBusy(null);
    }
  };

  const ack = async (id: string) => {
    try {
      await acknowledgeAlert(id);
      await load(filter);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not acknowledge that alert.");
    }
  };

  if (loading) {
    return (
      <div className="max-w-6xl mx-auto space-y-4">
        <div className="h-8 w-72 bg-slate-200 animate-pulse rounded-md" />
        <div className="h-32 bg-slate-200 animate-pulse rounded-2xl" />
        <div className="h-64 bg-slate-200 animate-pulse rounded-2xl" />
      </div>
    );
  }

  const openAlerts = alerts.filter((a) => !a.acknowledged);
  const highest = assessments[0];

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col lg:flex-row lg:items-center gap-4"
      >
        <div className="flex-1">
          <h1 className="text-xl md:text-2xl font-bold text-slate-800">AI Security</h1>
          <p className="text-slate-500 mt-1">
            Behavioural anomaly detection over record access. It analyses how records are
            touched — never what they contain.
          </p>
        </div>
        <div className="flex gap-2 flex-shrink-0">
          <button
            onClick={analyze}
            disabled={running}
            className="flex items-center gap-2 px-4 py-2.5 bg-cyan-600 hover:bg-cyan-700 text-white rounded-xl text-sm font-bold transition-colors disabled:opacity-60"
          >
            {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
            {running ? "Analysing…" : "Run Analysis"}
          </button>
        </div>
      </motion.div>

      {notice && (
        <div className="p-3 rounded-xl bg-cyan-50 border border-cyan-100 text-cyan-800 text-sm font-semibold flex items-start gap-2.5">
          <Check className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <span>{notice}</span>
          <button onClick={() => setNotice("")} className="ml-auto opacity-60 hover:opacity-100" aria-label="Dismiss">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}
      {error && (
        <div className="p-3 rounded-xl bg-rose-50 border border-rose-100 text-rose-700 text-sm font-semibold">
          {error}
        </div>
      )}

      {/* Summary. Counts only earn tiles here because triage starts with them. */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[
          { label: "Actors scored", value: assessments.length, icon: Brain, tint: "text-cyan-600 bg-cyan-50" },
          { label: "Open alerts", value: openAlerts.length, icon: AlertTriangle, tint: "text-amber-600 bg-amber-50" },
          { label: "Open incidents", value: incidents.filter(i => i.status !== "Closed").length, icon: FileWarning, tint: "text-rose-600 bg-rose-50" },
          { label: "Federated rounds", value: federated?.rounds_completed ?? 0, icon: Network, tint: "text-violet-600 bg-violet-50" },
        ].map((s) => (
          <div key={s.label} className="bg-white rounded-2xl shadow-sm border border-slate-100 p-4">
            <div className={`w-8 h-8 rounded-lg flex items-center justify-center mb-2 ${s.tint}`}>
              <s.icon className="w-4 h-4" />
            </div>
            <p className="text-2xl font-bold text-slate-800 tabular-nums">{s.value}</p>
            <p className="text-xs text-slate-500">{s.label}</p>
          </div>
        ))}
      </div>

      {/* Alerts first — this is a queue to work, not a report to read. */}
      {openAlerts.length > 0 && (
        <section className="bg-white rounded-2xl shadow-sm border border-slate-100 p-5">
          <h2 className="text-lg font-bold text-slate-800 mb-4 pb-3 border-b border-slate-100 flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-amber-500" /> Alerts needing attention
          </h2>
          <div className="space-y-3">
            {openAlerts.map((a) => (
              <div
                key={a.id}
                className={`p-4 rounded-xl border-l-4 ${
                  a.severity === "HIGH" ? "bg-rose-50/60 border-rose-400" : "bg-amber-50/60 border-amber-400"
                }`}
              >
                <div className="flex items-start gap-3 flex-wrap">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border uppercase tracking-wide ${LEVEL_STYLE[a.severity]}`}>
                        {a.severity}
                      </span>
                      <span className="text-xs font-mono font-bold text-slate-600">{a.response}</span>
                      {a.source && (
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-white border border-slate-200 text-slate-500">
                          {SOURCE_LABEL[a.source] || a.source}
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-slate-800 font-semibold mt-1.5">{a.title}</p>
                    <p className="text-sm text-slate-600 mt-1">{a.summary}</p>
                    <p className="text-xs text-slate-500 mt-1.5 italic">
                      {RESPONSE_HINT[a.response] || ""}
                    </p>
                  </div>
                  <button
                    onClick={() => ack(a.id)}
                    className="px-3 py-1.5 rounded-lg bg-white border border-slate-200 text-xs font-bold text-slate-700 hover:bg-slate-50 flex-shrink-0"
                  >
                    Acknowledge
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* The explainability panel — the point of the whole layer. */}
      <section className="bg-white rounded-2xl shadow-sm border border-slate-100 p-5">
        <div className="flex items-center gap-3 mb-4 pb-3 border-b border-slate-100 flex-wrap">
          <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2 flex-1">
            <Brain className="w-5 h-5 text-cyan-600" /> Risk assessments
          </h2>
          <div className="flex gap-1">
            {["", "HIGH", "MEDIUM", "LOW"].map((l) => (
              <button
                key={l || "all"}
                onClick={() => setFilter(l)}
                className={`px-2.5 py-1 rounded-lg text-xs font-bold transition-colors ${
                  filter === l ? "bg-slate-800 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                }`}
              >
                {l || "All"}
              </button>
            ))}
          </div>
        </div>

        {assessments.length === 0 ? (
          <div className="py-10 text-center text-slate-500">
            <Brain className="w-12 h-12 mx-auto text-slate-300 mb-3" />
            <p className="font-semibold text-slate-700">Nothing scored yet</p>
            <p className="text-sm mt-1">Run an analysis to score recent activity.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {assessments.map((a) => (
              <div key={a.id} className="border border-slate-100 rounded-xl overflow-hidden">
                <div className="flex items-center gap-3 p-3 bg-slate-50 flex-wrap">
                  <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border uppercase tracking-wide ${LEVEL_STYLE[a.risk_level]}`}>
                    {a.risk_level}
                  </span>
                  <span className="font-mono text-sm font-bold text-slate-800 tabular-nums">
                    {a.risk_score.toFixed(2)}
                  </span>
                  <span className="text-sm text-slate-700 font-semibold">
                    {a.actor_public_id || "—"}
                  </span>
                  <span className="text-xs text-slate-500">
                    {a.actor_name} · {a.actor_role}
                  </span>
                  <span className="ml-auto text-[10px] font-mono text-slate-400 uppercase tracking-wide">
                    {a.detection_source}
                  </span>
                </div>

                {a.explanation && a.explanation.length > 0 ? (
                  <div className="p-3">
                    <p className="text-[10px] uppercase font-bold text-slate-400 tracking-wide mb-2">
                      Why this was flagged
                      {a.explanation[0]?.source === "FEDERATED_CLASSIFIER" && " — matches confirmed threat patterns (trained classifier)"}
                    </p>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm min-w-[460px]">
                        <thead>
                          <tr className="text-left text-[10px] uppercase tracking-wide text-slate-400">
                            <th className="pb-1.5 font-bold">Indicator</th>
                            <th className="pb-1.5 font-bold text-right">Observed</th>
                            {a.explanation[0]?.source === "FEDERATED_CLASSIFIER" ? (
                              <>
                                <th className="pb-1.5 font-bold text-right">Learned weight</th>
                                <th className="pb-1.5 font-bold text-right">Contribution</th>
                              </>
                            ) : (
                              <>
                                <th className="pb-1.5 font-bold text-right">Peer median</th>
                                <th className="pb-1.5 font-bold text-right">Deviation</th>
                              </>
                            )}
                          </tr>
                        </thead>
                        <tbody className="tabular-nums">
                          {a.explanation.map((c) => (
                            <tr key={c.feature} className="border-t border-slate-50">
                              <td className="py-1.5 text-slate-700">{c.label}</td>
                              <td className="py-1.5 text-right font-semibold text-slate-800">{c.observed}</td>
                              {c.source === "FEDERATED_CLASSIFIER" ? (
                                <>
                                  <td className="py-1.5 text-right text-slate-500">{c.weight}</td>
                                  <td className="py-1.5 text-right text-rose-600 font-semibold">+{c.contribution}</td>
                                </>
                              ) : (
                                <>
                                  <td className="py-1.5 text-right text-slate-500">{c.peer_median}</td>
                                  <td className="py-1.5 text-right text-rose-600 font-semibold">{c.deviations}×</td>
                                </>
                              )}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ) : (
                  <p className="p-3 text-sm text-slate-500">{a.narrative}</p>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Incidents */}
      {incidents.length > 0 && (
        <section className="bg-white rounded-2xl shadow-sm border border-slate-100 p-5">
          <h2 className="text-lg font-bold text-slate-800 mb-4 pb-3 border-b border-slate-100 flex items-center gap-2">
            <FileWarning className="w-5 h-5 text-rose-500" /> Incident &amp; compliance records
          </h2>
          <div className="space-y-3">
            {incidents.map((i) => (
              <div key={i.incident_ref} className="p-4 rounded-xl bg-slate-50 border border-slate-100">
                <div className="flex items-center gap-2 flex-wrap mb-1.5">
                  <span className="font-mono text-xs font-bold text-slate-800">{i.incident_ref}</span>
                  <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border uppercase tracking-wide ${LEVEL_STYLE[i.risk_level]}`}>
                    {i.risk_level}
                  </span>
                  <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wide ${
                    i.status === "Open" ? "bg-rose-100 text-rose-700"
                      : i.status === "Investigating" ? "bg-amber-100 text-amber-800" : "bg-slate-200 text-slate-600"
                  }`}>
                    {i.status}
                  </span>
                  <span className="ml-auto text-xs text-slate-400">
                    {i.created_at ? new Date(i.created_at).toLocaleString() : ""}
                  </span>
                </div>
                <p className="text-sm font-semibold text-slate-800">
                  {i.event_type.replace(/_/g, " ")} · {i.actor_public_id}
                </p>
                <p className="text-sm text-slate-600 mt-1">{i.explanation}</p>
                <p className="text-xs text-slate-500 mt-1.5">
                  Affected: {i.affected_resource} · Detected by {SOURCE_LABEL[i.detection_source] || i.detection_source} · Response {i.response}
                </p>
                {i.status === "Closed" ? (
                  <p className="text-xs text-slate-600 mt-2 p-2 rounded-lg bg-white border border-slate-100">
                    <b>Resolution</b>{i.resolved_by ? ` (${i.resolved_by})` : ""}: {i.resolution}
                  </p>
                ) : closing === i.id ? (
                  <div className="mt-3 space-y-2">
                    <label htmlFor={`resolution-${i.id}`} className="block text-xs font-bold text-slate-500">
                      Resolution (required to close)
                    </label>
                    <textarea
                      id={`resolution-${i.id}`}
                      rows={2}
                      maxLength={2000}
                      value={resolution}
                      onChange={(e) => setResolution(e.target.value)}
                      placeholder="What was found, and what was done about it."
                      className="w-full p-2 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-200"
                    />
                    <label htmlFor={`verdict-${i.id}`} className="block text-xs font-bold text-slate-500">
                      Verdict (trains the threat classifier)
                    </label>
                    <select id={`verdict-${i.id}`} value={verdict}
                            onChange={(e) => setVerdict(e.target.value as IncidentVerdict | "")}
                            className="w-full p-2 rounded-lg border border-slate-200 text-sm bg-white">
                      <option value="">No verdict</option>
                      <option value="confirmed_threat">Confirmed threat</option>
                      <option value="false_positive">False positive</option>
                      <option value="inconclusive">Inconclusive</option>
                    </select>
                    <div className="flex gap-2">
                      <button
                        onClick={() => advanceIncident(i, "Closed")}
                        disabled={!resolution.trim() || incidentBusy === i.id}
                        className="px-3 py-1.5 rounded-lg bg-slate-800 text-white text-xs font-bold disabled:opacity-50 flex items-center gap-1.5"
                      >
                        {incidentBusy === i.id && <Loader2 className="w-3.5 h-3.5 animate-spin" />} Close incident
                      </button>
                      <button onClick={() => { setClosing(null); setResolution(""); setVerdict(""); }}
                              className="px-3 py-1.5 rounded-lg text-xs font-bold text-slate-600 hover:bg-white">
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="flex gap-2 mt-3">
                    {i.status === "Open" && (
                      <button
                        onClick={() => advanceIncident(i, "Investigating")}
                        disabled={incidentBusy === i.id}
                        className="px-3 py-1.5 rounded-lg bg-white border border-slate-200 text-xs font-bold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                      >
                        Start investigation
                      </button>
                    )}
                    <button
                      onClick={() => { setClosing(i.id); setResolution(""); setVerdict(""); }}
                      className="px-3 py-1.5 rounded-lg bg-white border border-slate-200 text-xs font-bold text-slate-700 hover:bg-slate-50"
                    >
                      Close with resolution
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Federated — with its honesty disclosure kept adjacent to the numbers. */}
      <section className="bg-white rounded-2xl shadow-sm border border-slate-100 p-5">
        <div className="flex items-center gap-3 mb-4 pb-3 border-b border-slate-100 flex-wrap">
          <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2 flex-1">
            <Network className="w-5 h-5 text-violet-500" /> Federated IDS
          </h2>
          <button
            onClick={federate}
            disabled={fedRunning}
            className="flex items-center gap-2 px-3 py-1.5 bg-violet-600 hover:bg-violet-700 text-white rounded-lg text-xs font-bold transition-colors disabled:opacity-60"
          >
            {fedRunning ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
            {fedRunning ? "Running…" : "Run Round"}
          </button>
        </div>

        {federated && (
          <>
            <div className="flex gap-6 flex-wrap text-sm mb-4">
              <span className="text-slate-600">
                Rounds <b className="text-slate-800 tabular-nums">{federated.rounds_completed}</b>
              </span>
              <span className="text-slate-600">
                Aggregation <b className="text-slate-800">{federated.aggregation}</b>
              </span>
              {federated.real_nodes !== undefined && (
                <span className="text-slate-600">
                  Latest round <b className="text-slate-800 tabular-nums">{federated.real_nodes}</b> real
                  {federated.simulated_nodes ? <> · <b className="tabular-nums">{federated.simulated_nodes}</b> simulated</> : null}
                </span>
              )}
            </div>
            {federated.detection_baseline && (
              <p className="text-sm text-slate-600 mb-4">
                Detection is scoring against: <b className="text-slate-800">{federated.detection_baseline}</b>
              </p>
            )}
            {federated.latest_round_adopted === false && (
              <p role="alert" className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mb-4">
                Round {federated.latest_round} was not adopted here: it would make detection on this
                hospital&apos;s data worse ({federated.latest_round_evaluation?.reasons.join("; ")}).
                Peers still receive it and judge it on their own data.
              </p>
            )}
            {!!federated.pending_peer_submissions && (
              <p className="text-xs text-slate-500 mb-4">
                {federated.pending_peer_submissions} peer update(s) waiting for round {federated.open_round}.
              </p>
            )}

            {federated.nodes.length > 0 && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mb-4">
                {federated.nodes.map((n) => (
                  <div
                    key={n.name}
                    className={`p-3 rounded-xl border flex items-center gap-3 ${
                      n.simulated ? "bg-slate-50 border-slate-200" : "bg-emerald-50 border-emerald-200"
                    }`}
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-slate-800 truncate">{n.name}</p>
                      <p className="text-xs text-slate-500 tabular-nums">{n.samples} samples</p>
                    </div>
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded uppercase tracking-wide flex-shrink-0 ${
                      n.simulated ? "bg-slate-200 text-slate-600" : "bg-emerald-100 text-emerald-700"
                    }`}>
                      {n.simulated ? "Simulated" : "Real"}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {/* Kept beside the numbers, not in a footnote: a reader who sees
                "4 nodes" must also see that three of them are not real. */}
            <div className={`p-3 rounded-xl border flex items-start gap-2.5 ${
              federated.status === "LIVE_FEDERATION" ? "bg-emerald-50 border-emerald-100" : "bg-amber-50 border-amber-100"
            }`}>
              {federated.status === "LIVE_FEDERATION"
                ? <ShieldCheck className="w-4 h-4 text-emerald-600 flex-shrink-0 mt-0.5" />
                : <ShieldAlert className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />}
              <p className={`text-xs ${federated.status === "LIVE_FEDERATION" ? "text-emerald-800" : "text-amber-800"}`}>
                {federated.disclosure}
              </p>
            </div>

            {/* Participation, the trained classifier, and which global model detection uses. */}
            <FederatedLearningPanel onChanged={() => load(filter)} />
          </>
        )}
      </section>

      {policy && (
        <section className="bg-white rounded-2xl shadow-sm border border-slate-100 p-5">
          <h2 className="text-lg font-bold text-slate-800 mb-4 pb-3 border-b border-slate-100 flex items-center gap-2">
            <SlidersHorizontal className="w-5 h-5 text-slate-500" /> Risk decision policy
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-sm">
            {[
              { label: `MEDIUM (≥ ${policy.risk_policy.thresholds.MEDIUM})`, action: policy.risk_policy.MEDIUM },
              { label: `HIGH (≥ ${policy.risk_policy.thresholds.HIGH})`, action: policy.risk_policy.HIGH },
              { label: "HIGH during an emergency", action: policy.risk_policy.EMERGENCY_HIGH },
            ].map((r) => (
              <div key={r.label} className="p-3 rounded-xl bg-slate-50 border border-slate-100">
                <p className="text-xs text-slate-500">{r.label}</p>
                <p className="font-bold text-slate-800 uppercase">{r.action}</p>
              </div>
            ))}
          </div>
          <p className="text-xs text-slate-500 mt-3">
            Re-verification lasts {policy.risk_policy.step_up_minutes} min · roles need at least{" "}
            {policy.risk_policy.min_peers} peers to be scored · break-glass limited to{" "}
            {policy.emergency_max_per_day} per doctor per day · scheduled analysis every{" "}
            {policy.scheduled_analysis_minutes || "—"} min · consent ledger: {policy.consent_ledger}.
            Configured through environment variables; see backend/.env.example.
          </p>
        </section>
      )}

      <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200 text-sm text-slate-600">
        <p className="font-bold text-slate-700 mb-1">What this layer does not do</p>
        <p>
          It never grants access. Authentication, role, relationship and consent decide that
          before any of this runs, and a low score cannot open a record they closed. What a
          high score does — alert, ask the user to re-enter their password, or refuse — is the
          configured policy above, applied after those checks, never instead of them.
        </p>
      </div>

      {highest && highest.risk_level === "HIGH" && (
        <p className="text-xs text-slate-400 text-center">
          Highest current score: {highest.risk_score.toFixed(2)} — {highest.actor_public_id}
        </p>
      )}
    </div>
  );
}
