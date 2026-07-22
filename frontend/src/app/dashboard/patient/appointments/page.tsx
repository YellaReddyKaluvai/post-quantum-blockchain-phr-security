"use client";

import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Calendar, Clock, User, Building, CalendarCheck, CalendarX2 } from "lucide-react";
import { getPatientAppointments } from "@/lib/session";

export default function AppointmentsPage() {
  const [loading, setLoading] = useState(true);
  const [appointments, setAppointments] = useState<any[]>([]);

  useEffect(() => {
    async function loadData() {
      try {
        const data = await getPatientAppointments();
        setAppointments(data);
      } catch (error) {
        console.error("Failed to load appointments:", error);
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
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="bg-white rounded-2xl p-6 h-40 animate-pulse shadow-sm border border-slate-100"></div>
          ))}
        </div>
      </div>
    );
  }

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const upcoming = appointments.filter(app => {
    const appDate = new Date(app.date);
    return app.status === 'Scheduled' && appDate >= today;
  }).sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());

  const previous = appointments.filter(app => {
    const appDate = new Date(app.date);
    return app.status !== 'Scheduled' || appDate < today;
  }).sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case "scheduled": return "bg-blue-100 text-blue-700 border-blue-200";
      case "completed": return "bg-emerald-100 text-emerald-700 border-emerald-200";
      case "cancelled": return "bg-rose-100 text-rose-700 border-rose-200";
      default: return "bg-slate-100 text-slate-700 border-slate-200";
    }
  };

  const AppointmentCard = ({ appointment, isUpcoming }: { appointment: any, isUpcoming: boolean }) => (
    <motion.div
      variants={{ hidden: { opacity: 0, scale: 0.95 }, show: { opacity: 1, scale: 1 } }}
      className={`bg-white rounded-2xl shadow-sm border overflow-hidden relative group ${isUpcoming ? "border-blue-100 hover:shadow-md ring-1 ring-blue-50" : "border-slate-100 opacity-90"}`}
    >
      <div className={`absolute top-0 left-0 w-1.5 h-full ${isUpcoming ? "bg-blue-400" : "bg-slate-300"}`}></div>
      <div className="p-5 pl-7">
        <div className="flex justify-between items-start mb-4">
          <div className="flex items-center gap-2">
            <span className="px-2.5 py-1 bg-slate-100 rounded-md text-xs font-bold text-slate-600">
              {appointment.department}
            </span>
          </div>
          <span className={`px-2.5 py-1 rounded-full text-xs font-bold border ${getStatusColor(appointment.status)}`}>
            {appointment.status}
          </span>
        </div>
        
        <h3 className="text-lg font-bold text-slate-800 mb-4 flex items-center gap-2">
          <User className="w-5 h-5 text-slate-400" /> Dr. {appointment.doctor_name}
        </h3>
        
        <div className="grid grid-cols-2 gap-3 bg-slate-50 p-3 rounded-xl border border-slate-100">
          <div className="flex flex-col">
            <span className="text-[10px] uppercase font-bold text-slate-400 mb-1 flex items-center gap-1"><Calendar className="w-3 h-3" /> Date</span>
            <span className="text-sm font-semibold text-slate-700">{new Date(appointment.date).toLocaleDateString()}</span>
          </div>
          <div className="flex flex-col">
            <span className="text-[10px] uppercase font-bold text-slate-400 mb-1 flex items-center gap-1"><Clock className="w-3 h-3" /> Time</span>
            <span className="text-sm font-semibold text-slate-700">{appointment.time}</span>
          </div>
        </div>
      </div>
    </motion.div>
  );

  return (
    <div className="max-w-7xl mx-auto space-y-8">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-xl md:text-2xl font-bold text-slate-800">Appointments</h1>
        <p className="text-slate-500 mt-1">Manage your upcoming and past medical appointments.</p>
      </motion.div>

      {/* Upcoming Appointments */}
      <div>
        <div className="flex items-center gap-2 mb-4">
          <CalendarCheck className="w-5 h-5 text-blue-500" />
          <h2 className="text-lg font-bold text-slate-800">Upcoming Appointments</h2>
        </div>
        
        {upcoming.length === 0 ? (
          <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-8 text-center border-dashed">
            <p className="text-slate-500">No upcoming appointments scheduled.</p>
          </div>
        ) : (
          <motion.div
            initial="hidden"
            animate="show"
            variants={{ show: { transition: { staggerChildren: 0.1 } } }}
            className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6"
          >
            {upcoming.map(app => (
              <AppointmentCard key={app.id} appointment={app} isUpcoming={true} />
            ))}
          </motion.div>
        )}
      </div>

      {/* Previous Appointments */}
      <div>
        <div className="flex items-center gap-2 mb-4">
          <CalendarX2 className="w-5 h-5 text-slate-500" />
          <h2 className="text-lg font-bold text-slate-800">Previous Appointments</h2>
        </div>
        
        {previous.length === 0 ? (
          <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-8 text-center border-dashed">
            <p className="text-slate-500">No previous appointments found.</p>
          </div>
        ) : (
          <motion.div
            initial="hidden"
            animate="show"
            variants={{ show: { transition: { staggerChildren: 0.1 } } }}
            className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6"
          >
            {previous.map(app => (
              <AppointmentCard key={app.id} appointment={app} isUpcoming={false} />
            ))}
          </motion.div>
        )}
      </div>
    </div>
  );
}
