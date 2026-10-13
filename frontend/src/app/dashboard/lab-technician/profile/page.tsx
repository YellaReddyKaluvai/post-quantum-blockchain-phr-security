"use client";

import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { User, Mail, Shield, Building, Award, RefreshCw } from "lucide-react";
import { getLabTechProfile } from "@/lib/session";

interface LabTechProfileInfo {
  id?: string;
  full_name?: string;
  email?: string;
  role?: string;
  gender?: string;
  department?: string;
  certification?: string;
  hospital_branch?: string;
  user_id?: string;
  status?: string;
  reports_generated?: number;
  created_at?: string;
}



export default function LabTechProfilePage() {
  const [profile, setProfile] = useState<LabTechProfileInfo | null>(null);

  const [loading, setLoading] = useState(true);

  const fetchProfile = async () => {
    setLoading(true);
    try {
      const data = await getLabTechProfile();
      setProfile(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProfile();
  }, []);

  if (loading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-8 bg-slate-200 rounded w-1/4" />
        <div className="h-64 bg-slate-200 rounded-2xl" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-extrabold text-slate-800">My Profile</h1>
          <p className="text-sm text-slate-500">Laboratory Technician Demographic & Department Details</p>
        </div>
        <button
          onClick={fetchProfile}
          className="flex items-center gap-2 px-4 py-2 bg-white border border-slate-200 text-slate-600 rounded-xl hover:bg-slate-50 transition-colors font-semibold text-sm shadow-sm"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Profile Card */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="md:col-span-1 bg-white rounded-2xl p-6 shadow-sm border border-slate-100 flex flex-col items-center text-center space-y-4"
        >
          <div className="w-24 h-24 rounded-full bg-gradient-to-br from-cyan-500 to-teal-600 flex items-center justify-center text-white text-3xl font-extrabold shadow-lg shadow-cyan-900/20">
            {profile?.full_name?.charAt(0) || "L"}
          </div>
          <div>
            <h2 className="text-xl font-bold text-slate-800">{profile?.full_name}</h2>
            <span className="inline-block mt-1 px-3 py-1 bg-cyan-50 text-cyan-700 font-semibold text-xs rounded-full border border-cyan-100">
              {profile?.role || "Lab Technician"}
            </span>
          </div>
          <div className="w-full pt-4 border-t border-slate-100 space-y-3 text-left">
            <div className="flex items-center gap-3 text-slate-600 text-sm">
              <Shield className="w-4 h-4 text-cyan-500 flex-shrink-0" />
              <div>
                <p className="text-xs text-slate-400">Technician ID</p>
                <p className="font-semibold">{profile?.user_id || "LAB-2026-000001"}</p>
              </div>
            </div>
            <div className="flex items-center gap-3 text-slate-600 text-sm">
              <Mail className="w-4 h-4 text-cyan-500 flex-shrink-0" />
              <div>
                <p className="text-xs text-slate-400">Email Address</p>
                <p className="font-semibold">{profile?.email}</p>
              </div>
            </div>
            <div className="flex items-center gap-3 text-slate-600 text-sm">
              <Building className="w-4 h-4 text-cyan-500 flex-shrink-0" />
              <div>
                <p className="text-xs text-slate-400">Department</p>
                <p className="font-semibold">{profile?.department || "Central Laboratory"}</p>
              </div>
            </div>
          </div>
        </motion.div>

        {/* Detailed Stats & Information */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="md:col-span-2 space-y-6"
        >
          <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-100 space-y-4">
            <h3 className="text-lg font-bold text-slate-800 border-b border-slate-100 pb-3 flex items-center gap-2">
              <Award className="w-5 h-5 text-cyan-500" />
              Performance & Activity
            </h3>
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-slate-50 p-4 rounded-xl border border-slate-100">
                <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Reports Generated</p>
                <p className="text-2xl font-extrabold text-slate-800 mt-1">{profile?.reports_generated || 0}</p>
              </div>
              <div className="bg-slate-50 p-4 rounded-xl border border-slate-100">
                <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Account Status</p>
                <span className="inline-block mt-2 px-2.5 py-1 bg-emerald-50 text-emerald-700 text-xs font-bold rounded-lg border border-emerald-100">
                  {profile?.status || "Approved"}
                </span>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-100 space-y-4">
            <h3 className="text-lg font-bold text-slate-800 border-b border-slate-100 pb-3 flex items-center gap-2">
              <User className="w-5 h-5 text-cyan-500" />
              Demographic Details
            </h3>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <p className="text-xs text-slate-400">Gender</p>
                <p className="font-semibold text-slate-800 mt-0.5">{profile?.gender || "N/A"}</p>
              </div>
              <div>
                <p className="text-xs text-slate-400">Joined System</p>
                <p className="font-semibold text-slate-800 mt-0.5">
                  {profile?.created_at ? new Date(profile.created_at).toLocaleDateString() : "2026-01-15"}
                </p>
              </div>
            </div>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
