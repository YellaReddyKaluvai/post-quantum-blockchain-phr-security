"use client";

import React, { useCallback, useEffect, useState } from "react";
import { Brain, CheckCircle, Download, Loader2, LogOut, RotateCcw, ShieldCheck, Upload, XCircle } from "lucide-react";
import {
  FederatedClassifierStatus, FederatedModelRecord, FederationParticipation,
  activateFederatedModel, getFederatedClassifierStatus, getFederatedModels, getFederationParticipation,
  joinFederation, leaveFederation, pullFromFederationHub, submitToFederationHub, switchToLocalModels,
} from "@/lib/session";

const pct = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${Math.round(v * 100)}%`);

/**
 * This hospital's part in federated learning (spec §20–21), inside the one
 * Federated IDS section: joining a federation, the trained threat classifier,
 * exchanging updates, and which global model detection uses — with the
 * evaluation each pulled model received here and a way back.
 */
export default function FederatedLearningPanel({ onChanged }: { onChanged: () => void }) {
  const [participation, setParticipation] = useState<FederationParticipation | null>(null);
  const [classifier, setClassifier] = useState<FederatedClassifierStatus | null>(null);
  const [models, setModels] = useState<FederatedModelRecord[]>([]);
  const [version, setVersion] = useState(0);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState("");
  const [form, setForm] = useState({ hub_url: "", node_name: "", shared_secret: "" });

  useEffect(() => {
    let live = true;
    Promise.all([getFederationParticipation(), getFederatedClassifierStatus(), getFederatedModels()])
      .then(([p, c, m]) => { if (live) { setParticipation(p); setClassifier(c); setModels(m); } })
      .catch((e) => { if (live) setError(e instanceof Error ? e.message : "Failed to load federation state"); });
    return () => { live = false; };
  }, [version]);

  const run = useCallback(async (key: string, action: () => Promise<string>) => {
    if (busy) return;
    setBusy(key);
    setError("");
    setMessage("");
    try {
      setMessage(await action());
      setVersion((v) => v + 1);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setBusy("");
    }
  }, [busy, onChanged]);

  const join = (e: React.FormEvent) => {
    e.preventDefault();
    run("join", async () => {
      await joinFederation({ hub_url: form.hub_url.trim(), node_name: form.node_name.trim(), shared_secret: form.shared_secret.trim() });
      setForm({ hub_url: "", node_name: "", shared_secret: "" });
      return "Joined. Submit a local update to take part in the next round.";
    });
  };

  const submit = () => run("submit", async () => {
    const r = await submitToFederationHub();
    const c = r.classifier;
    return `Submitted for hub round ${r.round_number}: baselines for ${r.roles.length} role(s)` +
      (c?.trained ? `, and the classifier trained on ${c.labels} investigated incidents` +
        (c.privacy?.dp ? ` (differentially private, ε=${c.privacy.epsilon})` : "") + "."
        : `. ${c?.note ?? ""}`);
  });

  const pull = () => run("pull", async () => {
    const r = await pullFromFederationHub();
    return r.note as string;
  });

  const input = "w-full px-3 py-2 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-violet-200";

  return (
    <div className="mt-4 pt-4 border-t border-slate-100 space-y-5">
      {message && <p className="text-sm font-semibold text-emerald-700 flex items-start gap-1.5"><CheckCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />{message}</p>}
      {error && <p role="alert" className="text-sm font-semibold text-rose-600">{error}</p>}

      {/* ── Participation ── */}
      <div>
        <p className="text-sm font-bold text-slate-700 mb-1">This hospital as a participant</p>
        {participation === null ? (
          <div className="h-10 rounded-lg bg-slate-50 animate-pulse" />
        ) : participation.configured ? (
          <>
            <p className="text-xs text-slate-500 mb-3">
              Hub <span className="font-mono">{participation.hub_url}</span> as{" "}
              <span className="font-mono">{participation.node_name}</span>
              {participation.source === "environment" ? " · set by the server environment" : ""}
              {participation.sync_interval_minutes ? ` · syncs every ${participation.sync_interval_minutes} min` : " · manual sync"}
              {participation.last_sync_at ? ` · last sync ${new Date(participation.last_sync_at).toLocaleString()}` : ""}
            </p>
            {participation.transport_warning && (
              <p role="alert" className="text-xs font-semibold text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mb-3">
                {participation.transport_warning}
              </p>
            )}
            <div className="flex gap-2 flex-wrap">
              <button onClick={submit} disabled={busy !== ""}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-violet-200 text-violet-700 text-xs font-bold hover:bg-violet-50 disabled:opacity-50">
                {busy === "submit" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
                Train &amp; submit local update
              </button>
              <button onClick={pull} disabled={busy !== ""}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-violet-200 text-violet-700 text-xs font-bold hover:bg-violet-50 disabled:opacity-50">
                {busy === "pull" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
                Pull &amp; evaluate global model
              </button>
              {participation.source === "database" && (
                <button onClick={() => { if (window.confirm("Leave this federation? Models already pulled are kept.")) run("leave", async () => { await leaveFederation(); return "Left the federation."; }); }}
                  disabled={busy !== ""}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold text-rose-600 hover:bg-rose-50 disabled:opacity-50">
                  <LogOut className="w-3.5 h-3.5" /> Leave
                </button>
              )}
            </div>
          </>
        ) : (
          <form onSubmit={join} className="grid grid-cols-1 md:grid-cols-3 gap-2" noValidate>
            <p className="md:col-span-3 text-xs text-slate-500">
              Join another hospital&apos;s federation with the details its administrator issued when registering this hospital as a peer.
              Only model parameters are ever sent — never records, events, labels or identifiers.
            </p>
            <div>
              <label htmlFor="fl-hub" className="block text-[11px] font-bold text-slate-500 mb-1">Hub address</label>
              <input id="fl-hub" className={input} placeholder="https://hub.example-hospital.org" value={form.hub_url}
                onChange={(e) => setForm((f) => ({ ...f, hub_url: e.target.value }))} />
            </div>
            <div>
              <label htmlFor="fl-node" className="block text-[11px] font-bold text-slate-500 mb-1">This hospital&apos;s node name</label>
              <input id="fl-node" className={input} placeholder="as registered by the hub" value={form.node_name}
                onChange={(e) => setForm((f) => ({ ...f, node_name: e.target.value }))} />
            </div>
            <div>
              <label htmlFor="fl-secret" className="block text-[11px] font-bold text-slate-500 mb-1">Shared secret</label>
              <input id="fl-secret" type="password" autoComplete="off" className={input} value={form.shared_secret}
                onChange={(e) => setForm((f) => ({ ...f, shared_secret: e.target.value }))} />
            </div>
            <div className="md:col-span-3 flex justify-end">
              <button type="submit"
                disabled={busy !== "" || !/^https?:\/\/\S+$/.test(form.hub_url.trim()) || form.node_name.trim().length < 2 || form.shared_secret.trim().length < 16}
                className="px-4 py-2 rounded-lg text-xs font-bold bg-violet-600 text-white hover:bg-violet-700 disabled:opacity-50 flex items-center gap-1.5">
                {busy === "join" && <Loader2 className="w-3.5 h-3.5 animate-spin" />} Join federation
              </button>
            </div>
          </form>
        )}
      </div>

      {/* ── The trained threat classifier ── */}
      {classifier && (
        <div>
          <p className="text-sm font-bold text-slate-700 mb-1 flex items-center gap-1.5"><Brain className="w-4 h-4 text-violet-500" /> Threat classifier</p>
          <p className="text-xs text-slate-500 mb-2">
            Trained on incidents your investigators closed with a verdict, then federated. Close incidents as
            &ldquo;confirmed threat&rdquo; or &ldquo;false positive&rdquo; to teach it.
          </p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
            <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100">
              <p className="text-slate-500">Investigated incidents</p>
              <p className="font-bold text-slate-800">{classifier.labels.threats} threats · {classifier.labels.benign} benign</p>
            </div>
            <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100">
              <p className="text-slate-500">Local training</p>
              <p className="font-bold text-slate-800">
                {classifier.trainable ? `fit ${pct(classifier.local_fit?.accuracy)} accuracy` : `needs ${classifier.needs.labels}, ${classifier.needs.per_class}+ of each`}
              </p>
            </div>
            <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100 md:col-span-2">
              <p className="text-slate-500">Detection is using</p>
              <p className="font-bold text-slate-800">
                {classifier.in_use ? `${classifier.in_use.label} · ${classifier.in_use.rounds} round(s)` : "no classifier yet (anomaly baselines only)"}
              </p>
            </div>
          </div>
          <p className="text-[11px] text-slate-400 mt-2 flex items-center gap-1">
            <ShieldCheck className="w-3.5 h-3.5" /> Updates clipped to {classifier.privacy.clip} ·{" "}
            {classifier.privacy.dp_epsilon ? `differential privacy ε=${classifier.privacy.dp_epsilon} per round` : classifier.privacy.note}
          </p>
          {classifier.privacy.dp_epsilon && classifier.privacy.spent && (
            <p className="text-[11px] text-slate-500 mt-1">
              {classifier.privacy.spent.epsilon_total !== null
                ? <>Spent across all rounds: <b>ε={classifier.privacy.spent.epsilon_total}</b> at δ={classifier.privacy.spent.delta}{" "}
                    ({classifier.privacy.spent.releases_noised} release(s))
                    {classifier.privacy.spent.budget_epsilon
                      ? ` · budget ε=${classifier.privacy.spent.budget_epsilon}, ${classifier.privacy.spent.budget_remaining} left`
                      : " · no total budget set"}</>
                : `${classifier.privacy.spent.releases_without_noise} earlier release(s) had no noise, so no overall guarantee is claimed.`}
            </p>
          )}
        </div>
      )}

      {/* ── Global models received, and which one is in use ── */}
      {models.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <p className="text-sm font-bold text-slate-700">Global models received</p>
            <button onClick={() => run("local", async () => { await switchToLocalModels(); return "Detection now uses this hospital's own models only."; })}
              disabled={busy !== "" || !models.some((m) => m.active)}
              className="ml-auto flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-bold text-slate-600 hover:bg-slate-50 disabled:opacity-40">
              <RotateCcw className="w-3.5 h-3.5" /> Use local models only
            </button>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs min-w-[560px]">
              <thead>
                <tr className="text-left text-[10px] uppercase tracking-wide text-slate-400">
                  <th className="pb-1.5">Hub round</th><th className="pb-1.5">Institutions</th><th className="pb-1.5">Classifier</th>
                  <th className="pb-1.5">Evaluated here</th><th className="pb-1.5" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {models.map((m) => (
                  <tr key={m.id}>
                    <td className="py-2 font-semibold text-slate-700">{m.hub_round}<span className="block font-normal text-[10px] text-slate-400">{new Date(m.pulled_at).toLocaleString()}</span></td>
                    <td className="py-2 text-slate-600">{m.real_nodes} real</td>
                    <td className="py-2 text-slate-600">{m.classifier ? `${m.classifier.nodes} trained · round ${m.classifier.rounds}` : "—"}</td>
                    <td className="py-2">
                      {m.adopted
                        ? <span className="inline-flex items-center gap-1 text-emerald-700"><CheckCircle className="w-3.5 h-3.5" /> passed
                            {m.evaluation?.classifier?.global?.accuracy != null ? ` · ${pct(m.evaluation.classifier.global.accuracy)} on local incidents` : ""}</span>
                        : <span className="inline-flex items-start gap-1 text-rose-600"><XCircle className="w-3.5 h-3.5 mt-px flex-shrink-0" /> refused: {m.evaluation?.reasons?.join("; ")}</span>}
                    </td>
                    <td className="py-2 text-right whitespace-nowrap">
                      {m.active ? (
                        <span className="px-2 py-0.5 rounded-full bg-violet-100 text-violet-700 text-[10px] font-bold">IN USE</span>
                      ) : (
                        <button
                          onClick={() => {
                            if (!m.adopted && !window.confirm("This model failed its evaluation here. Use it anyway?")) return;
                            run(`act-${m.id}`, async () => { await activateFederatedModel(m.id); return `Detection now uses hub round ${m.hub_round}.`; });
                          }}
                          disabled={busy !== ""}
                          className="px-2 py-0.5 rounded-lg text-[11px] font-bold text-violet-700 hover:bg-violet-50 disabled:opacity-50">
                          {busy === `act-${m.id}` ? <Loader2 className="w-3 h-3 animate-spin inline" /> : "Use this"}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
