"use client";

import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { User, Shield, Mail, Calendar, Activity } from "lucide-react";
import { getPatientProfile } from "@/lib/session";

interface PatientProfilePersonalInfo {
  name?: string;
  email?: string;
  gender?: string;
  dob?: string;
  blood_group?: string;
}

interface PatientProfileAccountInfo {
  user_id?: string;
  registration_date?: string;
  role?: string;
  status?: string;
}

interface PatientProfileData {
  personal_info?: PatientProfilePersonalInfo;
  account_info?: PatientProfileAccountInfo;
}

export default function PatientProfilePage() {
  const [loading, setLoading] = useState(true);
  const [profile, setProfile] = useState<PatientProfileData | null>(null);

  useEffect(() => {
    async function loadData() {
      try {
        const data = await getPatientProfile();
        setProfile(data);
      } catch (error) {
        console.error("Failed to load profile:", error);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="h-8 w-48 bg-slate-200 animate-pulse rounded-md"></div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="bg-white rounded-2xl p-6 h-64 animate-pulse shadow-sm border border-slate-100"></div>
          <div className="bg-white rounded-2xl p-6 h-64 animate-pulse shadow-sm border border-slate-100"></div>
        </div>
      </div>
    );
  }

  const containerVariants = {
    hidden: { opacity: 0 },
    show: {
      opacity: 1,
      transition: { staggerChildren: 0.1 }
    }
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    show: { opacity: 1, y: 0 }
  };

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-xl md:text-2xl font-bold text-slate-800">My Profile</h1>
        <p className="text-slate-500 mt-1">Manage your personal and account information.</p>
      </motion.div>

      <motion.div
        variants={containerVariants}
        initial="hidden"
        animate="show"
        className="grid grid-cols-1 md:grid-cols-2 gap-6"
      >
        {/* Personal Information */}
        <motion.div variants={itemVariants} className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
          <div className="p-6 border-b border-slate-100 flex items-center gap-3">
            <div className="p-2 bg-blue-50 text-blue-600 rounded-xl">
              <User className="w-5 h-5" />
            </div>
            <h2 className="text-lg font-bold text-slate-800">Personal Information</h2>
          </div>
          <div className="p-6 space-y-4">
            <div className="grid grid-cols-3 gap-4">
              <div className="col-span-1 text-sm text-slate-500 font-medium">Full Name</div>
              <div className="col-span-2 text-sm font-semibold text-slate-800">{profile?.personal_info?.name || "N/A"}</div>
            </div>
            <div className="grid grid-cols-3 gap-4">
              <div className="col-span-1 text-sm text-slate-500 font-medium">Email</div>
              <div className="col-span-2 text-sm font-semibold text-slate-800 flex items-center gap-2">
                <Mail className="w-4 h-4 text-slate-400" />
                {profile?.personal_info?.email || "N/A"}
              </div>
            </div>
            <div className="grid grid-cols-3 gap-4">
              <div className="col-span-1 text-sm text-slate-500 font-medium">Gender</div>
              <div className="col-span-2 text-sm font-semibold text-slate-800">{profile?.personal_info?.gender || "N/A"}</div>
            </div>
            <div className="grid grid-cols-3 gap-4">
              <div className="col-span-1 text-sm text-slate-500 font-medium">Date of Birth</div>
              <div className="col-span-2 text-sm font-semibold text-slate-800 flex items-center gap-2">
                <Calendar className="w-4 h-4 text-slate-400" />
                {profile?.personal_info?.dob ? new Date(profile.personal_info.dob).toLocaleDateString() : "N/A"}
              </div>
            </div>
            <div className="grid grid-cols-3 gap-4">
              <div className="col-span-1 text-sm text-slate-500 font-medium">Blood Group</div>
              <div className="col-span-2 text-sm font-semibold text-red-500 flex items-center gap-2">
                <Activity className="w-4 h-4" />
                {profile?.personal_info?.blood_group || "N/A"}
              </div>
            </div>
          </div>
        </motion.div>

        {/* Account Information */}
        <motion.div variants={itemVariants} className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
          <div className="p-6 border-b border-slate-100 flex items-center gap-3">
            <div className="p-2 bg-emerald-50 text-emerald-600 rounded-xl">
              <Shield className="w-5 h-5" />
            </div>
            <h2 className="text-lg font-bold text-slate-800">Account Information</h2>
          </div>
          <div className="p-6 space-y-4">
            <div className="grid grid-cols-3 gap-4">
              <div className="col-span-1 text-sm text-slate-500 font-medium">User ID</div>
              <div className="col-span-2 text-sm font-mono font-semibold text-slate-700 bg-slate-50 p-1.5 rounded w-fit">
                {profile?.account_info?.user_id || "N/A"}
              </div>
            </div>
            <div className="grid grid-cols-3 gap-4">
              <div className="col-span-1 text-sm text-slate-500 font-medium">Registration Date</div>
              <div className="col-span-2 text-sm font-semibold text-slate-800">
                {profile?.account_info?.registration_date ? new Date(profile.account_info.registration_date).toLocaleDateString() : "N/A"}
              </div>
            </div>
            <div className="grid grid-cols-3 gap-4">
              <div className="col-span-1 text-sm text-slate-500 font-medium">Role</div>
              <div className="col-span-2">
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-cyan-100 text-cyan-800">
                  {profile?.account_info?.role || "Patient"}
                </span>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-4">
              <div className="col-span-1 text-sm text-slate-500 font-medium">Account Status</div>
              <div className="col-span-2">
                <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${
                  profile?.account_info?.status === "Active" ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"
                }`}>
                  {profile?.account_info?.status || "Unknown"}
                </span>
              </div>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}
