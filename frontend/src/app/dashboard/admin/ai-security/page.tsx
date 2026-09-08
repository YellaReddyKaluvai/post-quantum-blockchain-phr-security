"use client";

import React, { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
import {
  Brain, AlertTriangle, FileWarning, Network, Play, Loader2, Check, X, ShieldAlert,
} from "lucide-react";
import {
  runSecurityAnalysis, getRiskAssessments, getSecurityAlerts,
  acknowledgeAlert, getSecurityIncidents, getFederatedStatus, runFederatedRound,
} from "@/lib/session";

interface Attribution {
  feature: string;
  label: string;
  observed: number;
  peer_median: number;
  deviations: number;
  contribution: number;
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
  actor_name?: string | null;
  actor_public_id?: string | null;
  acknowledged: boolean;
  created_at?: string | null;
}

interface Incident {
  incident_ref: string;
  event_type: string;
  affected_resource?: string | null;
  risk_level: string;
  detection_source: string;
  explanation?: string | null;
  response?: string | null;
  status: string;
  actor_name?: string | null;
  actor_public_id?: string | null;
  created_at?: string | null;
}

interface FederatedNode { name: string; simulated: boolean; samples: number; }
interface Federated {
  rounds_completed: number;
  latest_round?: number | null;
  aggregation: string;
  nodes: FederatedNode[];
  status: string;
  disclosure: string;
}

const LEVEL_STYLE: Record<string, string> = {
  HIGH: "bg-rose-50 text-rose-700 border-rose-200",
  MEDIUM: "bg-amber-50 text-amber-700 border-amber-200",
  LOW: "bg-emerald-50 text-emerald-700 border-emerald-200",
};

const RESPONSE_HINT: Record<string, string> = {
  MONITOR: "No action needed — recorded for context.",
  VERIFY: "Worth a look. Confirm the activity was legitimate.",
  ESCALATE: "Investigate now. An incident record was opened.",
};

export default function AiSecurityPage() {
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [federated, setFederated] = useState<Federated | null>(null);
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
          { label: "Incidents", value: incidents.filter(i => i.status === "Open").length, icon: FileWarning, tint: "text-rose-600 bg-rose-50" },
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
                    </p>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm min-w-[460px]">
                        <thead>
                          <tr className="text-left text-[10px] uppercase tracking-wide text-slate-400">
                            <th className="pb-1.5 font-bold">Indicator</th>
                            <th className="pb-1.5 font-bold text-right">Observed</th>
                            <th className="pb-1.5 font-bold text-right">Peer median</th>
                            <th className="pb-1.5 font-bold text-right">Deviation</th>
                          </tr>
                        </thead>
                        <tbody className="tabular-nums">
                          {a.explanation.map((c) => (
                            <tr key={c.feature} className="border-t border-slate-50">
                              <td className="py-1.5 text-slate-700">{c.label}</td>
                              <td className="py-1.5 text-right font-semibold text-slate-800">{c.observed}</td>
                              <td className="py-1.5 text-right text-slate-500">{c.peer_median}</td>
                              <td className="py-1.5 text-right text-rose-600 font-semibold">{c.deviations}×</td>
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
                    i.status === "Open" ? "bg-rose-100 text-rose-700" : "bg-slate-200 text-slate-600"
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
                  Affected: {i.affected_resource} · Detected by {i.detection_source} · Response {i.response}
                </p>
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
            </div>

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
            <div className="p-3 rounded-xl bg-amber-50 border border-amber-100 flex items-start gap-2.5">
              <ShieldAlert className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
              <p className="text-xs text-amber-800">{federated.disclosure}</p>
            </div>
          </>
        )}
      </section>

      <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200 text-sm text-slate-600">
        <p className="font-bold text-slate-700 mb-1">What this layer does not do</p>
        <p>
          It never grants or blocks access. Authentication, role, relationship and consent
          decide that before any of this runs. A risk score is a signal for a person to act
          on — not a gate between a clinician and a patient&rsquo;s record.
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
