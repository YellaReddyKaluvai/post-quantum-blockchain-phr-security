"use client";

import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Calendar, Check, X, Clock } from "lucide-react";
import { getDoctorAppointments, updateAppointmentStatus } from "@/lib/session";

interface DoctorAppointment {
  id: string;
  patient_name?: string;
  status?: string;
  date?: string;
  time?: string;
  [key: string]: unknown;
}

export default function Appointments() {
  const [appointments, setAppointments] = useState<DoctorAppointment[]>([]);

  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchAppts() {
      try {
        const data = await getDoctorAppointments();
        setAppointments(data);
      } catch (error) {
        console.error("Error fetching appointments:", error);
      } finally {
        setLoading(false);
      }
    }
    fetchAppts();
  }, []);

  const handleAction = async (id: string, action: string) => {
    try {
      await updateAppointmentStatus(id, action);
      // Update local state mockingly
      setAppointments(appointments.map(a => 
        a.id === id 
          ? { ...a, status: action === "accept" ? "Confirmed" : action === "cancel" ? "Cancelled" : "Completed" } 
          : a
      ));
    } catch (error) {
      console.error(error);
    }
  };

  if (loading) {
    return <div className="space-y-4">{[1,2,3].map(i => <div key={i} className="h-24 bg-slate-200 animate-pulse rounded-2xl" />)}</div>;
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center gap-3 mb-6">
        <Calendar className="w-6 h-6 text-indigo-600" />
        <h1 className="text-2xl font-bold text-slate-800">Appointments</h1>
      </div>

      <div className="space-y-4">
        {appointments.length === 0 ? (
          <div className="text-center py-12 bg-white rounded-2xl shadow-sm border border-slate-100 text-slate-500">
            No appointments found.
          </div>
        ) : (
          appointments.map((appt: DoctorAppointment, i: number) => (
            <motion.div
              key={appt.id || i}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
              className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-4"
            >
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <h3 className="font-bold text-slate-800">{appt.patient_name}</h3>
                  <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold uppercase ${
                    appt.status === 'Confirmed' ? 'bg-indigo-100 text-indigo-700' :
                    appt.status === 'Completed' ? 'bg-emerald-100 text-emerald-700' :
                    appt.status === 'Cancelled' ? 'bg-rose-100 text-rose-700' :
                    'bg-amber-100 text-amber-700'
                  }`}>
                    {appt.status || "Pending"}
                  </span>
                </div>
                <div className="flex items-center gap-4 text-sm text-slate-600">
                  <span className="flex items-center gap-1"><Calendar className="w-4 h-4" /> {new Date(appt.date || Date.now()).toLocaleDateString()}</span>
                  <span className="flex items-center gap-1"><Clock className="w-4 h-4" /> {appt.time}</span>
                </div>
              </div>


              <div className="flex gap-2">
                {(appt.status === "Pending" || appt.status === "Scheduled") && (
                  <>
                    <button onClick={() => handleAction(appt.id, "accept")} className="px-3 py-1.5 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 rounded-xl text-sm font-semibold transition-colors flex items-center gap-1">
                      <Check className="w-4 h-4" /> Accept
                    </button>
                    <button onClick={() => handleAction(appt.id, "cancel")} className="px-3 py-1.5 bg-rose-50 hover:bg-rose-100 text-rose-700 rounded-xl text-sm font-semibold transition-colors flex items-center gap-1">
                      <X className="w-4 h-4" /> Cancel
                    </button>
                  </>
                )}
                {appt.status === "Confirmed" && (
                  <button onClick={() => handleAction(appt.id, "complete")} className="px-3 py-1.5 bg-cyan-50 hover:bg-cyan-100 text-cyan-700 rounded-xl text-sm font-semibold transition-colors flex items-center gap-1">
                    <Check className="w-4 h-4" /> Complete
                  </button>
                )}
              </div>
            </motion.div>
          ))
        )}
      </div>
    </div>
  );
}
