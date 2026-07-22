"use client";

import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Activity, Users, Calendar, FileText, HeartPulse } from "lucide-react";
import { getDoctorDashboardSummary } from "@/lib/session";

export default function DoctorDashboard() {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    async function fetchData() {
      try {
        const result = await getDoctorDashboardSummary();
        setData(result);
      } catch (error) {
        console.error("Error fetching doctor dashboard summary:", error);
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-32 bg-slate-200 animate-pulse rounded-2xl" />
          ))}
        </div>
        <div className="h-64 bg-slate-200 animate-pulse rounded-2xl" />
      </div>
    );
  }

  const stats = data?.stats || {
    assigned_patients: 0,
    todays_appointments: 0,
    pending_reports: 0,
    recent_diagnoses: 0,
  };

  const statCards = [
    { label: "Assigned Patients", value: stats.assigned_patients, icon: Users, color: "text-blue-500", bg: "bg-blue-50" },
    { label: "Today's Appointments", value: stats.todays_appointments, icon: Calendar, color: "text-indigo-500", bg: "bg-indigo-50" },
    { label: "Pending Reports", value: stats.pending_reports, icon: FileText, color: "text-amber-500", bg: "bg-amber-50" },
    { label: "Recent Diagnoses", value: stats.recent_diagnoses, icon: HeartPulse, color: "text-emerald-500", bg: "bg-emerald-50" },
  ];

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-6"
      >
        {statCards.map((stat, i) => (
          <div
            key={i}
            className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100 flex items-center gap-4"
          >
            <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${stat.bg}`}>
              <stat.icon className={`w-6 h-6 ${stat.color}`} />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-500">{stat.label}</p>
              <h3 className="text-2xl font-bold text-slate-800">{stat.value}</h3>
            </div>
          </div>
        ))}
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="bg-white rounded-2xl shadow-sm border border-slate-100 p-6"
      >
        <div className="flex items-center gap-3 mb-6 border-b border-slate-100 pb-4">
          <Activity className="w-5 h-5 text-cyan-500" />
          <h2 className="text-lg font-bold text-slate-800">Recent Activities</h2>
        </div>
        <div className="space-y-4">
          {data?.recent_activities?.length > 0 ? (
            data.recent_activities.map((activity: any, i: number) => (
              <div key={i} className="flex items-start gap-4 pb-4 border-b border-slate-50 last:border-0">
                <div className="w-2 h-2 mt-2 rounded-full bg-cyan-400" />
                <div>
                  <p className="text-sm font-medium text-slate-800">{activity.description}</p>
                  <p className="text-xs text-slate-500">{new Date(activity.timestamp).toLocaleString()}</p>
                </div>
              </div>
            ))
          ) : (
            <p className="text-sm text-slate-500">No recent activities found.</p>
          )}
        </div>
      </motion.div>
    </div>
  );
}
