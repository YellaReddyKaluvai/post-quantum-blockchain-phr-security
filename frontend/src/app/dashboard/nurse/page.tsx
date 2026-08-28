"use client";

import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Users, Activity, ClipboardList, Pill, Clock } from "lucide-react";
import { getNurseDashboardSummary } from "@/lib/session";

interface NurseActivityItem {
  title?: string;
  description?: string;
  created_at?: string;
  [key: string]: unknown;
}

interface NurseSummary {
  patients_attended_today?: number;
  vitals_recorded_today?: number;
  notes_added_today?: number;
  medications_administered_today?: number;
  recent_activities?: NurseActivityItem[];
  [key: string]: unknown;
}

export default function NurseDashboardHome() {
  const [summary, setSummary] = useState<NurseSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchSummary() {
      try {
        const data = await getNurseDashboardSummary();
        setSummary(data);
      } catch (error) {
        console.error("Failed to load nurse dashboard summary:", error);
      } finally {
        setLoading(false);
      }
    }
    fetchSummary();
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100 animate-pulse h-32" />
          ))}
        </div>
        <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100 animate-pulse h-96" />
      </div>
    );
  }

  const statCards = [
    { label: "Patients Attended Today", value: summary?.patients_attended_today ?? 0, icon: Users, color: "text-cyan-600", bg: "bg-cyan-50" },
    { label: "Vitals Recorded Today", value: summary?.vitals_recorded_today ?? 0, icon: Activity, color: "text-emerald-600", bg: "bg-emerald-50" },
    { label: "Notes Added Today", value: summary?.notes_added_today ?? 0, icon: ClipboardList, color: "text-amber-600", bg: "bg-amber-50" },
    { label: "Medications Administered", value: summary?.medications_administered_today ?? 0, icon: Pill, color: "text-blue-600", bg: "bg-blue-50" },
  ];

  const activities = summary?.recent_activities ?? [];

  return (
    <div className="space-y-8">
      {/* Stat Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {statCards.map((stat, idx) => (
          <motion.div
            key={idx}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: idx * 0.1 }}
            className="bg-white/80 backdrop-blur-md p-6 rounded-2xl shadow-sm border border-slate-100 flex flex-col justify-between"
          >
            <div className="flex justify-between items-start mb-4">
              <div className={`p-3 rounded-xl ${stat.bg}`}>
                <stat.icon className={`w-6 h-6 ${stat.color}`} />
              </div>
            </div>
            <div>
              <p className="text-3xl font-bold text-slate-800">{stat.value}</p>
              <p className="text-sm font-medium text-slate-500 mt-1">{stat.label}</p>
            </div>
          </motion.div>
        ))}
      </div>

      {/* Recent Activity */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4 }}
        className="bg-white/80 backdrop-blur-md rounded-2xl shadow-sm border border-slate-100 overflow-hidden"
      >
        <div className="px-6 py-5 border-b border-slate-100 bg-slate-50/50">
          <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
            <Clock className="w-5 h-5 text-cyan-600" />
            Recent Activity
          </h2>
        </div>
        <div className="p-6">
          {activities.length === 0 ? (
            <p className="text-sm text-slate-500">No recent activity found.</p>
          ) : (
            <div className="space-y-6">
              {activities.map((activity, idx) => (
                <div key={idx} className="flex gap-4">
                  <div className="flex flex-col items-center">
                    <div className="w-3 h-3 rounded-full mt-1.5 bg-cyan-400" />
                    {idx !== activities.length - 1 && <div className="w-0.5 h-full bg-slate-100 mt-2" />}
                  </div>
                  <div className="pb-6">
                    <p className="text-sm font-medium text-slate-800">{activity.title}</p>
                    <p className="text-xs text-slate-500 mt-1">
                      {activity.description}
                      {activity.created_at ? ` · ${new Date(activity.created_at).toLocaleString()}` : ""}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </motion.div>
    </div>
  );
}
