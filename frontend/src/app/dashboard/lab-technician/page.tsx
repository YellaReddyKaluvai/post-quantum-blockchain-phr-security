"use client";

import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { FlaskConical, FileText, ClipboardList, Share2, AlertCircle, Clock } from "lucide-react";
import { getLabTechDashboardSummary } from "@/lib/session";

export default function LabTechnicianDashboard() {
  const [summary, setSummary] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchSummary = async () => {
      try {
        const data = await getLabTechDashboardSummary();
        setSummary(data);
      } catch (error) {
        console.error(error);
        // Fallback mock data
        setSummary({
          testsAssigned: 42,
          reportsGenerated: 28,
          pendingRequests: 14,
          reportsShared: 25,
          awaitingReview: 5,
          recentActivity: [
            { id: 1, action: "Report Generated for John Doe (CBC)", time: "10 mins ago", type: "success" },
            { id: 2, action: "New Test Request: MRI Scan (Jane Smith)", time: "1 hour ago", type: "info" },
            { id: 3, action: "Urgent: Blood Sugar test pending for Mark Johnson", time: "2 hours ago", type: "warning" },
          ]
        });
      } finally {
        setLoading(false);
      }
    };
    fetchSummary();
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-6">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100 animate-pulse h-32" />
          ))}
        </div>
        <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100 animate-pulse h-96" />
      </div>
    );
  }

  const statCards = [
    { label: "Tests Assigned Today", value: summary.testsAssigned, icon: FlaskConical, color: "text-cyan-600", bg: "bg-cyan-50" },
    { label: "Reports Generated", value: summary.reportsGenerated, icon: FileText, color: "text-emerald-600", bg: "bg-emerald-50" },
    { label: "Pending Requests", value: summary.pendingRequests, icon: ClipboardList, color: "text-amber-600", bg: "bg-amber-50" },
    { label: "Reports Shared", value: summary.reportsShared, icon: Share2, color: "text-blue-600", bg: "bg-blue-50" },
    { label: "Awaiting Review", value: summary.awaitingReview, icon: AlertCircle, color: "text-rose-600", bg: "bg-rose-50" },
  ];

  return (
    <div className="space-y-8">
      {/* Stat Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-6">
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
        transition={{ delay: 0.5 }}
        className="bg-white/80 backdrop-blur-md rounded-2xl shadow-sm border border-slate-100 overflow-hidden"
      >
        <div className="px-6 py-5 border-b border-slate-100 bg-slate-50/50">
          <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
            <Clock className="w-5 h-5 text-cyan-600" />
            Recent Activity
          </h2>
        </div>
        <div className="p-6">
          <div className="space-y-6">
            {summary.recentActivity.map((activity: any, idx: number) => (
              <div key={idx} className="flex gap-4">
                <div className="flex flex-col items-center">
                  <div className={`w-3 h-3 rounded-full mt-1.5 ${
                    activity.type === 'success' ? 'bg-emerald-400' :
                    activity.type === 'warning' ? 'bg-amber-400' :
                    'bg-cyan-400'
                  }`} />
                  {idx !== summary.recentActivity.length - 1 && (
                    <div className="w-0.5 h-full bg-slate-100 mt-2" />
                  )}
                </div>
                <div className="pb-6">
                  <p className="text-sm font-medium text-slate-800">{activity.action}</p>
                  <p className="text-xs text-slate-500 mt-1">{activity.time}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </motion.div>
    </div>
  );
}
