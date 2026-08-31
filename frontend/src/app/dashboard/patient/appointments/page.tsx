"use client";

import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Calendar, Clock, User, CalendarCheck, CalendarX2, Plus, X, Loader2 } from "lucide-react";
import { getPatientAppointments, getAvailableDoctors, createPatientAppointment } from "@/lib/session";

interface AppointmentItem {
  id: string;
  doctor_name?: string;
  department?: string;
  appointment_date?: string;
  appointment_time?: string;
  time?: string;
  status?: string;
  notes?: string;
  [key: string]: unknown;
}

interface DoctorOption {
  id: string;
  full_name: string;
  specialization?: string | null;
}

function BookAppointmentModal({ onClose, onBooked }: { onClose: () => void; onBooked: () => void }) {
  const [doctors, setDoctors] = useState<DoctorOption[]>([]);
  const [doctorId, setDoctorId] = useState("");
  const [department, setDepartment] = useState("");
  const [appointmentDate, setAppointmentDate] = useState("");
  const [appointmentTime, setAppointmentTime] = useState("");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [loadingDoctors, setLoadingDoctors] = useState(true);

  useEffect(() => {
    getAvailableDoctors()
      .then((rows: DoctorOption[]) => setDoctors(rows))
      .catch(() => setError("Failed to load doctor list."))
      .finally(() => setLoadingDoctors(false));
  }, []);

  useEffect(() => {
    const selected = doctors.find((d) => d.id === doctorId);
    if (selected?.specialization && !department) {
      setDepartment(selected.specialization);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doctorId]);

  const todayStr = new Date().toISOString().split("T")[0];

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (!doctorId || !department || !appointmentDate || !appointmentTime) {
      setError("Please fill in all required fields.");
      return;
    }
    try {
      setSubmitting(true);
      await createPatientAppointment({
        doctor_id: doctorId,
        department,
        appointment_date: appointmentDate,
        appointment_time: appointmentTime,
        notes: notes || undefined,
      });
      onBooked();
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to book appointment.");
    } finally {
      setSubmitting(false);
    }
  };

  const inputClass = "w-full bg-slate-50 border border-slate-200 rounded-xl py-2.5 px-3.5 text-sm font-medium text-slate-800 focus:outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 transition-all";
  const labelClass = "block text-xs font-bold text-slate-500 mb-1.5 uppercase tracking-wide";

  return (
    <motion.div
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center z-50 p-4"
      onClick={onClose}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95 }}
        className="bg-white rounded-2xl shadow-xl max-w-md w-full p-6 relative"
        onClick={(e) => e.stopPropagation()}
      >
        <button onClick={onClose} className="absolute top-4 right-4 text-slate-400 hover:text-slate-700">
          <X className="w-5 h-5" />
        </button>
        <h2 className="text-lg font-bold text-slate-800 mb-1">Book Appointment</h2>
        <p className="text-sm text-slate-500 mb-5">Request a new appointment with a doctor.</p>

        {error && <div className="p-3 mb-4 rounded-xl bg-rose-50 border border-rose-100 text-rose-600 text-xs font-semibold">{error}</div>}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className={labelClass}>Doctor</label>
            <select value={doctorId} onChange={(e) => setDoctorId(e.target.value)} className={inputClass} disabled={loadingDoctors} required>
              <option value="">{loadingDoctors ? "Loading doctors..." : "Select a doctor"}</option>
              {doctors.map((d) => (
                <option key={d.id} value={d.id}>
                  Dr. {d.full_name}{d.specialization ? ` — ${d.specialization}` : ""}
                </option>
              ))}
            </select>
            {!loadingDoctors && doctors.length === 0 && (
              <p className="text-xs text-amber-600 mt-1">No approved doctors are currently available.</p>
            )}
          </div>

          <div>
            <label className={labelClass}>Department</label>
            <input type="text" value={department} onChange={(e) => setDepartment(e.target.value)} className={inputClass} placeholder="e.g. Cardiology" required />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelClass}>Date</label>
              <input type="date" min={todayStr} value={appointmentDate} onChange={(e) => setAppointmentDate(e.target.value)} className={inputClass} required />
            </div>
            <div>
              <label className={labelClass}>Time</label>
              <input type="time" value={appointmentTime} onChange={(e) => setAppointmentTime(e.target.value)} className={inputClass} required />
            </div>
          </div>

          <div>
            <label className={labelClass}>Notes (optional)</label>
            <textarea value={notes} onChange={(e) => setNotes(e.target.value)} className={inputClass} rows={2} placeholder="Reason for visit..." />
          </div>

          <button
            type="submit"
            disabled={submitting}
            className="w-full bg-gradient-to-r from-blue-500 to-cyan-500 hover:from-blue-400 hover:to-cyan-400 text-white py-3 rounded-xl font-bold transition-all flex items-center justify-center gap-2 disabled:opacity-60"
          >
            {submitting ? <><Loader2 className="w-4 h-4 animate-spin" /> Booking...</> : "Request Appointment"}
          </button>
        </form>
      </motion.div>
    </motion.div>
  );
}

export default function AppointmentsPage() {
  const [loading, setLoading] = useState(true);
  const [appointments, setAppointments] = useState<AppointmentItem[]>([]);
  const [showBookModal, setShowBookModal] = useState(false);

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

  useEffect(() => {
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

  // A booking still awaiting doctor confirmation ("Pending") or already
  // confirmed ("Confirmed"/"Scheduled") both belong in "Upcoming" as long as
  // the date hasn't passed. Only Completed/Cancelled, or a past date, moves an
  // appointment into "Previous".
  const activeStatuses = new Set(["scheduled", "confirmed", "pending"]);

  const upcoming = appointments.filter((app: AppointmentItem) => {
    const dateStr = (app.appointment_date || app.date || "") as string | number | Date;
    const appDate = new Date(dateStr);
    return activeStatuses.has((app.status || "").toLowerCase()) && appDate >= today;
  }).sort((a: AppointmentItem, b: AppointmentItem) => new Date((a.appointment_date || a.date || "") as string | number | Date).getTime() - new Date((b.appointment_date || b.date || "") as string | number | Date).getTime());

  const previous = appointments.filter((app: AppointmentItem) => {
    const dateStr = (app.appointment_date || app.date || "") as string | number | Date;
    const appDate = new Date(dateStr);
    return !activeStatuses.has((app.status || "").toLowerCase()) || appDate < today;
  }).sort((a: AppointmentItem, b: AppointmentItem) => new Date((b.appointment_date || b.date || "") as string | number | Date).getTime() - new Date((a.appointment_date || a.date || "") as string | number | Date).getTime());

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case "scheduled":
      case "confirmed": return "bg-blue-100 text-blue-700 border-blue-200";
      case "pending": return "bg-amber-100 text-amber-700 border-amber-200";
      case "completed": return "bg-emerald-100 text-emerald-700 border-emerald-200";
      case "cancelled": return "bg-rose-100 text-rose-700 border-rose-200";
      default: return "bg-slate-100 text-slate-700 border-slate-200";
    }
  };

  const AppointmentCard = ({ appointment, isUpcoming }: { appointment: AppointmentItem, isUpcoming: boolean }) => (
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
          <span className={`px-2.5 py-1 rounded-full text-xs font-bold border ${getStatusColor(appointment.status || "Scheduled")}`}>

            {appointment.status}
          </span>
        </div>
        
        <h3 className="text-lg font-bold text-slate-800 mb-4 flex items-center gap-2">
          <User className="w-5 h-5 text-slate-400" /> Dr. {appointment.doctor_name}
        </h3>
        
        <div className="grid grid-cols-2 gap-3 bg-slate-50 p-3 rounded-xl border border-slate-100">
          <div className="flex flex-col">
            <span className="text-[10px] uppercase font-bold text-slate-400 mb-1 flex items-center gap-1"><Calendar className="w-3 h-3" /> Date</span>
            <span className="text-sm font-semibold text-slate-700">{new Date((appointment.appointment_date || appointment.date || "") as string | number | Date).toLocaleDateString()}</span>

          </div>
          <div className="flex flex-col">
            <span className="text-[10px] uppercase font-bold text-slate-400 mb-1 flex items-center gap-1"><Clock className="w-3 h-3" /> Time</span>
            <span className="text-sm font-semibold text-slate-700">{appointment.appointment_time || appointment.time}</span>

          </div>
        </div>
      </div>
    </motion.div>
  );

  return (
    <div className="max-w-7xl mx-auto space-y-8">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-xl md:text-2xl font-bold text-slate-800">Appointments</h1>
          <p className="text-slate-500 mt-1">Manage your upcoming and past medical appointments.</p>
        </div>
        <button
          onClick={() => setShowBookModal(true)}
          className="flex items-center gap-2 bg-gradient-to-r from-blue-500 to-cyan-500 hover:from-blue-400 hover:to-cyan-400 text-white px-5 py-2.5 rounded-xl font-bold text-sm shadow-md shadow-blue-100 transition-all"
        >
          <Plus className="w-4 h-4" /> Book Appointment
        </button>
      </motion.div>

      <AnimatePresence>
        {showBookModal && (
          <BookAppointmentModal onClose={() => setShowBookModal(false)} onBooked={loadData} />
        )}
      </AnimatePresence>

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
