"use client";

import React, { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Network, Plus, Copy, Check, KeyRound, Loader2, Power, PowerOff, Clock, Globe, RefreshCw } from "lucide-react";
import { getFederatedPeers, registerFederatedPeer, rotateFederatedPeerSecret, setFederatedPeerActive } from "@/lib/session";

interface Peer {
  id: string;
  node_name: string;
  contact_url?: string | null;
  is_active: boolean;
  submissions: number;
  last_submission_at?: string | null;
  secret_rotated_at?: string | null;
  created_at?: string | null;
}

interface PeerList {
  peers: Peer[];
  total: number;
  active_contributors: number;
}

interface IssuedSecret {
  node_name: string;
  shared_secret: string;
  rotated?: boolean;
}

export default function AdminFederationPage() {
  const [data, setData] = useState<PeerList | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  const [nodeName, setNodeName] = useState("");
  const [contactUrl, setContactUrl] = useState("");
  const [registering, setRegistering] = useState(false);
  const [formError, setFormError] = useState("");
  const [issued, setIssued] = useState<IssuedSecret | null>(null);
  const [copied, setCopied] = useState(false);

  const [busyPeer, setBusyPeer] = useState<string | null>(null);
  const [rowError, setRowError] = useState("");

  const load = useCallback(async () => {
    try {
      setData(await getFederatedPeers());
      setLoadError("");
    } catch (error) {
      console.error(error);
      setLoadError("Could not load federation peers. Check that the backend is running.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const register = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError("");
    setRegistering(true);
    try {
      const result = await registerFederatedPeer(nodeName.trim(), contactUrl.trim() || undefined);
      setIssued({ node_name: result.node_name, shared_secret: result.shared_secret });
      setCopied(false);
      setNodeName("");
      setContactUrl("");
      await load();
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Could not register that peer");
    } finally {
      setRegistering(false);
    }
  };

  const toggle = async (peer: Peer) => {
    setRowError("");
    setBusyPeer(peer.id);
    try {
      await setFederatedPeerActive(peer.id, !peer.is_active);
      await load();
    } catch (error) {
      setRowError(error instanceof Error ? error.message : "Could not update that peer");
    } finally {
      setBusyPeer(null);
    }
  };

  const rotate = async (peer: Peer) => {
    if (!window.confirm(`Issue ${peer.node_name} a new secret? The current one stops working immediately.`)) return;
    setRowError("");
    setBusyPeer(peer.id);
    try {
      const result = await rotateFederatedPeerSecret(peer.id);
      setIssued({ node_name: result.node_name, shared_secret: result.shared_secret, rotated: true });
      setCopied(false);
      await load();
    } catch (error) {
      setRowError(error instanceof Error ? error.message : "Could not rotate that peer's secret");
    } finally {
      setBusyPeer(null);
    }
  };

  const copySecret = async () => {
    if (!issued) return;
    try {
      await navigator.clipboard.writeText(issued.shared_secret);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-8 w-64 bg-slate-200 animate-pulse rounded-md" />
        {[1, 2].map((i) => <div key={i} className="h-28 bg-slate-200 animate-pulse rounded-2xl" />)}
      </div>
    );
  }

  const nameValid = nodeName.trim().length >= 3 && nodeName.trim().length <= 120;

  return (
    <>
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
        <div className="flex items-center gap-3 mb-1">
          <Network className="w-7 h-7 text-cyan-600" />
          <h2 className="text-2xl sm:text-3xl font-extrabold text-slate-800">Federation Peers</h2>
        </div>
        <p className="text-sm text-slate-500">
          Other institutions that contribute anomaly-detection parameters to the federated rounds.
        </p>
      </motion.div>

      {loadError && (
        <div className="mb-6 p-3 rounded-xl bg-rose-50 border border-rose-100 text-rose-700 text-sm font-semibold">
          {loadError}
        </div>
      )}

      <div className="mb-6 p-4 rounded-2xl bg-slate-50 border border-slate-200 text-sm text-slate-600">
        <p className="font-bold text-slate-700 mb-1">What a peer sends, and what it never sends</p>
        <p>
          A peer fits its own baseline locally and submits only the resulting parameters — medians and
          scales — to <code className="font-mono text-xs bg-white px-1 py-0.5 rounded border border-slate-200">/api/federated/submit</code>.
          No record, event or identifier crosses the boundary. Each submission is signed with HMAC-SHA256
          using the secret issued below; an unsigned or wrongly signed submission is refused, and so is
          one from a suspended peer, one replayed or more than five minutes old, and one for a round that
          has not opened. A suspended peer&apos;s earlier updates are left out of new rounds. Simulated nodes
          in a round are separate and always labelled as such.
        </p>
      </div>

      {data && (
        <div className="grid grid-cols-2 gap-4 mb-6">
          <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-5">
            <p className="text-xs uppercase font-bold text-slate-400 tracking-wide">Registered peers</p>
            <p className="text-3xl font-extrabold text-slate-800 tabular-nums mt-1">{data.total}</p>
          </div>
          <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-5">
            <p className="text-xs uppercase font-bold text-slate-400 tracking-wide">Have submitted</p>
            <p className="text-3xl font-extrabold text-slate-800 tabular-nums mt-1">{data.active_contributors}</p>
          </div>
        </div>
      )}

      {/* Registration. The secret is shown exactly once, so it gets its own panel
          that stays until the admin dismisses it. */}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-5 mb-6">
        <h3 className="text-lg font-bold text-slate-800 mb-3 flex items-center gap-2">
          <Plus className="w-5 h-5 text-cyan-600" /> Register a peer
        </h3>
        <form onSubmit={register} className="grid grid-cols-1 sm:grid-cols-[1fr_1fr_auto] gap-3 items-start">
          <div>
            <label htmlFor="peer-name" className="block text-xs font-bold text-slate-500 mb-1">Node name</label>
            <input
              id="peer-name"
              value={nodeName}
              onChange={(e) => setNodeName(e.target.value)}
              placeholder="e.g. city-general-hospital"
              maxLength={120}
              className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-200"
            />
            <p className="text-[11px] text-slate-400 mt-1">The name the peer will sign its submissions with.</p>
          </div>
          <div>
            <label htmlFor="peer-url" className="block text-xs font-bold text-slate-500 mb-1">Contact URL (optional)</label>
            <input
              id="peer-url"
              value={contactUrl}
              onChange={(e) => setContactUrl(e.target.value)}
              placeholder="https://peer.example.org"
              maxLength={500}
              className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-200"
            />
          </div>
          <button
            type="submit"
            disabled={!nameValid || registering}
            className="sm:mt-5 px-4 py-2 rounded-xl bg-cyan-600 text-white text-sm font-bold hover:bg-cyan-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {registering ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
            Register
          </button>
        </form>
        {formError && <p className="mt-3 text-sm font-semibold text-rose-600">{formError}</p>}

        {issued && (
          <div className="mt-4 p-4 rounded-xl bg-amber-50 border border-amber-200">
            <p className="text-sm font-bold text-amber-900 flex items-center gap-2 mb-1">
              <KeyRound className="w-4 h-4" /> {issued.rotated ? "New shared secret" : "Shared secret"} for {issued.node_name}
            </p>
            <p className="text-xs text-amber-900 mb-3">
              Shown once. Give it to the peer institution over a secure channel — it is stored encrypted
              here and cannot be displayed again. If it is lost or may have leaked, rotate it.
              {issued.rotated && " The previous secret has stopped working."}
            </p>
            <div className="flex items-center gap-2">
              <code className="flex-1 font-mono text-xs bg-white border border-amber-200 rounded-lg px-3 py-2 break-all">
                {issued.shared_secret}
              </code>
              <button
                type="button"
                onClick={copySecret}
                className="px-3 py-2 rounded-lg bg-white border border-amber-200 text-amber-900 text-xs font-bold hover:bg-amber-100 flex items-center gap-1"
              >
                {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                {copied ? "Copied" : "Copy"}
              </button>
            </div>
            <button
              type="button"
              onClick={() => setIssued(null)}
              className="mt-3 text-xs font-bold text-amber-800 underline"
            >
              I have stored it — hide
            </button>
          </div>
        )}
      </div>

      {rowError && (
        <div className="mb-4 p-3 rounded-xl bg-rose-50 border border-rose-100 text-rose-700 text-sm font-semibold">
          {rowError}
        </div>
      )}

      {data && data.peers.length === 0 ? (
        <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-12 text-center">
          <Network className="w-14 h-14 mx-auto text-slate-300 mb-4" />
          <h3 className="text-lg font-bold text-slate-700">No Peers Registered</h3>
          <p className="text-slate-500 mt-1">
            Federated rounds run over simulated nodes until a real institution submits.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {data?.peers.map((peer, idx) => (
            <motion.div
              key={peer.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.04 }}
              className={`bg-white rounded-2xl shadow-sm border p-5 ${
                peer.is_active ? "border-slate-100" : "border-slate-200 opacity-75"
              }`}
            >
              <div className="flex items-start justify-between gap-4 flex-wrap">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap mb-1">
                    <span className="font-bold text-slate-800 break-all">{peer.node_name}</span>
                    <span className={`text-[10px] font-bold px-2.5 py-1 rounded-full uppercase tracking-wide ${
                      peer.is_active ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"
                    }`}>
                      {peer.is_active ? "Active" : "Suspended"}
                    </span>
                  </div>
                  {peer.contact_url && (
                    <p className="text-xs text-slate-500 flex items-center gap-1 break-all">
                      <Globe className="w-3 h-3 flex-shrink-0" /> {peer.contact_url}
                    </p>
                  )}
                  <p className="text-xs text-slate-400 flex items-center gap-1 mt-1">
                    <Clock className="w-3 h-3" />
                    {peer.submissions > 0
                      ? `${peer.submissions} submission${peer.submissions > 1 ? "s" : ""}, last ${
                          peer.last_submission_at ? new Date(peer.last_submission_at).toLocaleString() : "—"}`
                      : "Has not submitted yet"}
                    {peer.secret_rotated_at && ` · secret rotated ${new Date(peer.secret_rotated_at).toLocaleString()}`}
                  </p>
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => rotate(peer)}
                    disabled={busyPeer === peer.id}
                    className="px-3 py-2 rounded-xl text-xs font-bold flex items-center gap-1.5 border bg-white border-amber-200 text-amber-800 hover:bg-amber-50 disabled:opacity-50"
                  >
                    <RefreshCw className="w-3.5 h-3.5" /> Rotate secret
                  </button>
                  <button
                    type="button"
                    onClick={() => toggle(peer)}
                    disabled={busyPeer === peer.id}
                    className={`px-3 py-2 rounded-xl text-xs font-bold flex items-center gap-1.5 border disabled:opacity-50 ${
                      peer.is_active
                        ? "bg-white border-rose-200 text-rose-700 hover:bg-rose-50"
                        : "bg-white border-emerald-200 text-emerald-700 hover:bg-emerald-50"
                    }`}
                  >
                    {busyPeer === peer.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      : peer.is_active ? <PowerOff className="w-3.5 h-3.5" /> : <Power className="w-3.5 h-3.5" />}
                    {peer.is_active ? "Suspend" : "Reinstate"}
                  </button>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </>
  );
}
