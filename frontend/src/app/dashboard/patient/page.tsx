"use client";

import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { User, FileHeart, TestTubes, Calendar, Activity, Clock } from "lucide-react";
import { getPatientDashboardSummary } from "@/lib/session";

interface PatientActivityItem {
  title?: string;
  body?: string;
  description?: string;
  date?: string;
  created_at?: string;
  [key: string]: unknown;
}

interface PatientSummaryData {
  full_name?: string;
  patient_info?: { name?: string; user_id?: string; blood_group?: string; assigned_doctor?: string; [key: string]: unknown };
  medical_summary?: { latest_diagnosis?: string; current_treatment?: string; latest_prescription?: string; [key: string]: unknown };
  reports_summary?: { total_reports?: number; total?: number; latest_report?: string; pending_reports?: number; pending?: number; latest_report_date?: string; [key: string]: unknown };
  appointments_summary?: { upcoming_appointment?: { date?: string; doctor?: string }; upcoming_date?: string; previous_visit?: { date?: string; doctor?: string }; previous_visit_date?: string; [key: string]: unknown };
  recent_activities?: PatientActivityItem[];
  [key: string]: unknown;
}




export default function PatientDashboardHome() {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<PatientSummaryData | null>(null);

  useEffect(() => {
    async function loadData() {
      try {
        const summary = await getPatientDashboardSummary();
        setData(summary);
      } catch (error) {
        console.error("Failed to load dashboard summary:", error);
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
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="bg-white rounded-2xl shadow-sm border border-slate-100 p-6 h-40 animate-pulse">
              <div className="h-10 w-10 bg-slate-200 rounded-full mb-4"></div>
              <div className="h-4 w-24 bg-slate-200 rounded mb-2"></div>
              <div className="h-6 w-32 bg-slate-200 rounded"></div>
            </div>
          ))}
        </div>
        <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-6 h-64 animate-pulse mt-6"></div>
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
    <div className="space-y-6 max-w-7xl mx-auto">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-2xl font-bold text-slate-800">Welcome, {data?.patient_info?.name || "Patient"}</h1>
        <p className="text-slate-500 mt-1">Here is a summary of your health records and activities.</p>
      </motion.div>

      <motion.div
        variants={containerVariants}
        initial="hidden"
        animate="show"
        className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6"
      >
        {/* Patient Info Card */}
        <motion.div variants={itemVariants} className="bg-white rounded-2xl shadow-sm hover:shadow-lg transition-shadow border border-slate-100 p-6 relative overflow-hidden group">
          <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-blue-400 to-blue-600"></div>
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2.5 bg-blue-50 text-blue-600 rounded-xl group-hover:scale-110 transition-transform">
              <User className="w-6 h-6" />
            </div>
            <h3 className="font-semibold text-slate-700">Patient Info</h3>
          </div>
          <div className="space-y-2 text-sm">
            <p className="flex justify-between"><span className="text-slate-500">ID:</span> <span className="font-medium text-slate-800">{data?.patient_info?.user_id || "N/A"}</span></p>
            <p className="flex justify-between"><span className="text-slate-500">Blood:</span> <span className="font-medium text-slate-800">{data?.patient_info?.blood_group || "N/A"}</span></p>
            <p className="flex justify-between"><span className="text-slate-500">Doctor:</span> <span className="font-medium text-slate-800">{data?.patient_info?.assigned_doctor || "Not Assigned"}</span></p>
          </div>
        </motion.div>

        {/* Medical Summary Card */}
        <motion.div variants={itemVariants} className="bg-white rounded-2xl shadow-sm hover:shadow-lg transition-shadow border border-slate-100 p-6 relative overflow-hidden group">
          <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-teal-400 to-teal-600"></div>
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2.5 bg-teal-50 text-teal-600 rounded-xl group-hover:scale-110 transition-transform">
              <FileHeart className="w-6 h-6" />
            </div>
            <h3 className="font-semibold text-slate-700">Medical Summary</h3>
          </div>
          <div className="space-y-2 text-sm">
            <p className="flex flex-col"><span className="text-slate-500">Latest Diagnosis:</span> <span className="font-medium text-slate-800 truncate">{data?.medical_summary?.latest_diagnosis || "None"}</span></p>
            <p className="flex flex-col mt-1"><span className="text-slate-500">Latest Prescription:</span> <span className="font-medium text-slate-800 truncate">{data?.medical_summary?.latest_prescription || "None"}</span></p>
          </div>
        </motion.div>

        {/* Reports Card */}
        <motion.div variants={itemVariants} className="bg-white rounded-2xl shadow-sm hover:shadow-lg transition-shadow border border-slate-100 p-6 relative overflow-hidden group">
          <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-emerald-400 to-emerald-600"></div>
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2.5 bg-emerald-50 text-emerald-600 rounded-xl group-hover:scale-110 transition-transform">
              <TestTubes className="w-6 h-6" />
            </div>
            <h3 className="font-semibold text-slate-700">Lab Reports</h3>
          </div>
          <div className="space-y-2 text-sm">
            <p className="flex justify-between"><span className="text-slate-500">Total:</span> <span className="font-medium text-slate-800">{data?.reports_summary?.total || 0}</span></p>
            <p className="flex justify-between"><span className="text-slate-500">Pending:</span> <span className="font-medium text-amber-600">{data?.reports_summary?.pending || 0}</span></p>
            <p className="flex justify-between mt-1"><span className="text-slate-500">Latest:</span> <span className="font-medium text-slate-800 truncate max-w-[100px] text-right">{data?.reports_summary?.latest_report_date ? new Date(data.reports_summary.latest_report_date).toLocaleDateString() : "N/A"}</span></p>
          </div>
        </motion.div>

        {/* Appointments Card */}
        <motion.div variants={itemVariants} className="bg-white rounded-2xl shadow-sm hover:shadow-lg transition-shadow border border-slate-100 p-6 relative overflow-hidden group">
          <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-violet-400 to-violet-600"></div>
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2.5 bg-violet-50 text-violet-600 rounded-xl group-hover:scale-110 transition-transform">
              <Calendar className="w-6 h-6" />
            </div>
            <h3 className="font-semibold text-slate-700">Appointments</h3>
          </div>
          <div className="space-y-2 text-sm">
            <p className="flex flex-col"><span className="text-slate-500">Upcoming:</span> <span className="font-medium text-slate-800">{data?.appointments_summary?.upcoming_date ? new Date(data.appointments_summary.upcoming_date).toLocaleDateString() : "No upcoming"}</span></p>
            <p className="flex flex-col mt-1"><span className="text-slate-500">Previous Visit:</span> <span className="font-medium text-slate-800">{data?.appointments_summary?.previous_visit_date ? new Date(data.appointments_summary.previous_visit_date).toLocaleDateString() : "None"}</span></p>
          </div>
        </motion.div>
      </motion.div>

      {/* Recent Activities */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4 }}
        className="bg-white rounded-2xl shadow-sm border border-slate-100 p-6"
      >
        <div className="flex items-center gap-2 mb-6">
          <Activity className="w-5 h-5 text-slate-600" />
          <h2 className="text-lg font-bold text-slate-800">Recent Activities</h2>
        </div>
        
        {data?.recent_activities && data.recent_activities.length > 0 ? (
          <div className="space-y-6">
            {((data?.recent_activities || []) as PatientActivityItem[]).map((activity: PatientActivityItem, index: number) => (

              <div key={index} className="flex gap-4 relative">
                {index !== (data?.recent_activities || []).length - 1 && (
                  <div className="absolute top-8 left-[11px] bottom-[-24px] w-0.5 bg-slate-100"></div>
                )}
                <div className="w-6 h-6 rounded-full bg-cyan-100 flex items-center justify-center flex-shrink-0 mt-0.5 relative z-10 border-2 border-white shadow-sm">
                  <Clock className="w-3 h-3 text-cyan-600" />
                </div>
                <div>
                  <p className="text-sm font-medium text-slate-800">{activity.description}</p>
                  <p className="text-xs text-slate-500 mt-1">{new Date((activity.created_at || activity.date || Date.now()) as string | number | Date).toLocaleString()}</p>

                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-8">
            <Clock className="w-12 h-12 text-slate-200 mx-auto mb-3" />
            <p className="text-slate-500">No recent activities found.</p>
          </div>
        )}
      </motion.div>
    </div>
  );
}
