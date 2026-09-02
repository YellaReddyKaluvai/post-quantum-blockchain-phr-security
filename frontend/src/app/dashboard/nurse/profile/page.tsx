"use client";

import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { User, ShieldCheck, Mail, BadgeCheck, Building2 } from "lucide-react";
import { getNurseProfile } from "@/lib/session";

// Mirrors the backend NurseProfile.
interface NurseProfileInfo {
  id?: string;
  user_id?: string;
  full_name?: string;
  email?: string;
  role?: string;
  gender?: string;
  ward?: string;
  status?: string;
  created_at?: string;
}

export default function NurseProfilePage() {
  const [profile, setProfile] = useState<NurseProfileInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    getNurseProfile()
      .then(setProfile)
      .catch((error) => {
        console.error(error);
        setLoadError("Could not load your profile. Check that the backend is running.");
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <div className="max-w-3xl mx-auto h-80 bg-slate-200 animate-pulse rounded-2xl" />;
  }

  if (loadError) {
    return (
      <div className="max-w-3xl mx-auto p-4 rounded-xl bg-rose-50 border border-rose-100 text-rose-700 text-sm font-semibold">
        {loadError}
      </div>
    );
  }

  const fields = [
    { label: "User ID", value: profile?.user_id, icon: BadgeCheck },
    { label: "Email", value: profile?.email, icon: Mail },
    { label: "Gender", value: profile?.gender, icon: User },
    { label: "Ward", value: profile?.ward, icon: Building2 },
  ];

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">My Profile</h1>
        <p className="text-sm text-slate-500">Your account details and security status.</p>
      </div>

      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-white rounded-2xl shadow-sm border border-slate-100 p-6"
      >
        <div className="flex items-center gap-5 pb-6 border-b border-slate-100">
          <div className="w-20 h-20 rounded-full bg-cyan-100 flex items-center justify-center flex-shrink-0 text-2xl font-bold text-cyan-700">
            {profile?.full_name?.charAt(0) || "N"}
          </div>
          <div>
            <h2 className="text-2xl font-bold text-slate-800">{profile?.full_name || "—"}</h2>
            <p className="text-cyan-600 font-semibold">{profile?.role || "Nurse"}</p>
            {profile?.status && (
              <span className="inline-block mt-1.5 text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded bg-emerald-50 text-emerald-700">
                {profile.status}
              </span>
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-6">
          {fields.map((f) => (
            <div key={f.label}>
              <label className="text-xs font-bold text-slate-400 uppercase tracking-wide flex items-center gap-1.5 mb-1.5">
                <f.icon className="w-3.5 h-3.5" /> {f.label}
              </label>
              <p className="text-sm font-medium text-slate-700 bg-slate-50 py-2 px-3 rounded-xl border border-slate-100">
                {f.value || "—"}
              </p>
            </div>
          ))}
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="bg-white rounded-2xl shadow-sm border border-slate-100 p-6"
      >
        <div className="flex items-center gap-3 mb-4 pb-4 border-b border-slate-100">
          <ShieldCheck className="w-5 h-5 text-cyan-500" />
          <h2 className="text-lg font-bold text-slate-800">Account Security</h2>
        </div>
        <div className="space-y-2 text-sm text-slate-600">
          <p className="flex justify-between">
            <span>Post-quantum keypair</span>
            <span className="font-semibold text-emerald-600">Issued on approval</span>
          </p>
          <p className="flex justify-between">
            <span>Account created</span>
            <span className="font-medium text-slate-800">
              {profile?.created_at ? new Date(profile.created_at).toLocaleDateString() : "—"}
            </span>
          </p>
        </div>
        <p className="text-xs text-slate-500 mt-4">
          Your ML-KEM and ML-DSA keys were generated when an administrator approved your
          account. They protect the records you access; you never handle them directly.
        </p>
      </motion.div>
    </div>
  );
}
