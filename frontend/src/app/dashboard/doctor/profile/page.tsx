"use client";

import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { User, ShieldCheck } from "lucide-react";
import { getDoctorProfile } from "@/lib/session";

interface DoctorProfileInfo {
  id?: string;
  name?: string;
  full_name?: string;
  email?: string;
  role?: string;
  gender?: string;
  specialization?: string;
  qualification?: string;
  experience?: string;
  hospital_branch?: string;
  contact_number?: string;
  user_id?: string;
  status?: string;
  [key: string]: unknown;
}


export default function Profile() {
  const [profile, setProfile] = useState<DoctorProfileInfo | null>(null);

  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchProfile() {
      try {
        const data = await getDoctorProfile();
        setProfile(data);
      } catch (error) {
        console.error("Error fetching profile:", error);
      } finally {
        setLoading(false);
      }
    }
    fetchProfile();
  }, []);

  if (loading) {
    return <div className="h-64 bg-slate-200 animate-pulse rounded-2xl max-w-2xl mx-auto" />;
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div className="flex items-center gap-3 mb-6">
        <User className="w-6 h-6 text-cyan-600" />
        <h1 className="text-2xl font-bold text-slate-800">My Profile</h1>
      </div>

      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="bg-white p-8 rounded-2xl shadow-sm border border-slate-100 relative overflow-hidden">
        <div className="absolute top-0 right-0 p-6 opacity-10 pointer-events-none">
          <ShieldCheck className="w-48 h-48 text-cyan-500" />
        </div>
        
        <div className="relative z-10 flex flex-col md:flex-row items-center md:items-start gap-8">
          <div className="w-24 h-24 rounded-full bg-gradient-to-br from-cyan-400 to-teal-500 flex items-center justify-center shadow-lg shadow-cyan-900/20 flex-shrink-0 text-white text-3xl font-bold">
            {profile?.full_name?.charAt(0) || "D"}
          </div>
          
          <div className="flex-1 w-full space-y-6">
            <div>
              <h2 className="text-2xl font-bold text-slate-800">{profile?.full_name || "—"}</h2>
              <p className="text-cyan-600 font-semibold">{profile?.specialization || "—"}</p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
              <div>
                <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Doctor ID</p>
                <p className="text-sm font-medium text-slate-700 bg-slate-50 py-2 px-3 rounded-xl border border-slate-100">{profile?.user_id || "N/A"}</p>
              </div>
              <div>
                <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Email</p>
                <p className="text-sm font-medium text-slate-700 bg-slate-50 py-2 px-3 rounded-xl border border-slate-100">{profile?.email || "N/A"}</p>
              </div>
              <div>
                <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Gender</p>
                <p className="text-sm font-medium text-slate-700 bg-slate-50 py-2 px-3 rounded-xl border border-slate-100">{profile?.gender || "N/A"}</p>
              </div>
            </div>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
