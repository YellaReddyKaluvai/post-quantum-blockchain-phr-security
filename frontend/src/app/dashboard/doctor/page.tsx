"use client";

import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Activity, Users, Calendar, FileText, HeartPulse, Plus, X,
  Stethoscope, Pill, Shield, CheckCircle, Loader2
} from "lucide-react";
import { getDoctorDashboardSummary, searchDoctorPatients, createDiagnosis, createPrescription } from "@/lib/session";
import PatientSearchSelect from "@/components/PatientSearchSelect";

interface PatientResult {
  id: string;
  user_id: string;
  full_name: string;
  email: string;
  gender: string;
}

type ModalType = "diagnosis" | "prescription" | null;

export default function DoctorDashboard() {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [activeModal, setActiveModal] = useState<ModalType>(null);
  const [selectedPatient, setSelectedPatient] = useState<PatientResult | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  // Diagnosis form
  const [diagTitle, setDiagTitle] = useState("");
  const [diagDesc, setDiagDesc] = useState("");
  const [diagSymptoms, setDiagSymptoms] = useState("");
  const [diagNotes, setDiagNotes] = useState("");

  // Prescription form
  const [rxMedicine, setRxMedicine] = useState("");
  const [rxDosage, setRxDosage] = useState("");
  const [rxFrequency, setRxFrequency] = useState("");
  const [rxDuration, setRxDuration] = useState("");
  const [rxInstructions, setRxInstructions] = useState("");

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

  const resetForms = () => {
    setSelectedPatient(null);
    setDiagTitle(""); setDiagDesc(""); setDiagSymptoms(""); setDiagNotes("");
    setRxMedicine(""); setRxDosage(""); setRxFrequency(""); setRxDuration(""); setRxInstructions("");
    setSubmitting(false); setSubmitted(false);
  };

  const openModal = (type: ModalType) => {
    resetForms();
    setActiveModal(type);
  };

  const closeModal = () => {
    setActiveModal(null);
    resetForms();
  };

  const handleDiagnosisSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedPatient) return;
    setSubmitting(true);
    try {
      await createDiagnosis(selectedPatient.id, {
        title: diagTitle,
        description: diagDesc,
        symptoms: diagSymptoms,
        doctor_notes: diagNotes,
        visit_date: new Date().toISOString().split("T")[0],
      });
      setSubmitted(true);
      setTimeout(closeModal, 1500);
    } catch (err) {
      console.error("Failed to submit diagnosis:", err);
      alert("Failed to submit diagnosis. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const handlePrescriptionSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedPatient) return;
    setSubmitting(true);
    try {
      await createPrescription(selectedPatient.id, {
        medicine_name: rxMedicine,
        dosage: rxDosage,
        frequency: rxFrequency,
        duration: rxDuration,
        instructions: rxInstructions,
        prescribed_date: new Date().toISOString().split("T")[0],
      });
      setSubmitted(true);
      setTimeout(closeModal, 1500);
    } catch (err) {
      console.error("Failed to submit prescription:", err);
      alert("Failed to submit prescription. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

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

  const stats = (data?.stats || {}) as Record<string, number>;

  const statCards = [
    { label: "Assigned Patients", value: stats.assigned_patients || 0, icon: Users, color: "text-blue-500", bg: "bg-blue-50" },
    { label: "Today's Appointments", value: stats.todays_appointments || 0, icon: Calendar, color: "text-indigo-500", bg: "bg-indigo-50" },
    { label: "Pending Reports", value: stats.pending_reports || 0, icon: FileText, color: "text-amber-500", bg: "bg-amber-50" },
    { label: "Recent Diagnoses", value: stats.recent_diagnoses || 0, icon: HeartPulse, color: "text-emerald-500", bg: "bg-emerald-50" },
  ];


  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Stats Cards */}
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

      {/* Quick Actions Panel */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.05 }}
        className="bg-white rounded-2xl shadow-sm border border-slate-100 p-6"
      >
        <div className="flex items-center gap-3 mb-5 border-b border-slate-100 pb-4">
          <Shield className="w-5 h-5 text-cyan-500" />
          <h2 className="text-lg font-bold text-slate-800">Quick Actions</h2>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <button
            onClick={() => openModal("diagnosis")}
            className="flex items-center gap-4 p-5 bg-gradient-to-br from-cyan-50 to-blue-50 border border-cyan-100 rounded-2xl hover:shadow-md hover:border-cyan-200 transition-all group"
          >
            <div className="w-12 h-12 rounded-xl bg-cyan-100 flex items-center justify-center group-hover:bg-cyan-200 transition-colors">
              <Stethoscope className="w-6 h-6 text-cyan-600" />
            </div>
            <div className="text-left">
              <p className="text-sm font-bold text-slate-800">New Diagnosis</p>
              <p className="text-xs text-slate-500">Search patient & record diagnosis</p>
            </div>
          </button>
          <button
            onClick={() => openModal("prescription")}
            className="flex items-center gap-4 p-5 bg-gradient-to-br from-emerald-50 to-teal-50 border border-emerald-100 rounded-2xl hover:shadow-md hover:border-emerald-200 transition-all group"
          >
            <div className="w-12 h-12 rounded-xl bg-emerald-100 flex items-center justify-center group-hover:bg-emerald-200 transition-colors">
              <Pill className="w-6 h-6 text-emerald-600" />
            </div>
            <div className="text-left">
              <p className="text-sm font-bold text-slate-800">Write Prescription</p>
              <p className="text-xs text-slate-500">Search patient & prescribe medication</p>
            </div>
          </button>
        </div>
      </motion.div>

      {/* Recent Activities */}
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
          {((data?.recent_activities as Record<string, unknown>[])?.length > 0) ? (
            ((data?.recent_activities || []) as Record<string, unknown>[]).map((act: Record<string, unknown>, i: number) => (

              <div key={i} className="flex items-start gap-4 pb-4 border-b border-slate-50 last:border-0">
                <div className="w-2 h-2 mt-2 rounded-full bg-cyan-400" />
                <div>
                  <p className="text-sm font-medium text-slate-800">{act.description as string || act.title as string || act.body as string}</p>
                  <p className="text-xs text-slate-500">{act.timestamp ? new Date(act.timestamp as string).toLocaleString() : act.created_at ? new Date(act.created_at as string).toLocaleString() : ""}</p>
                </div>
              </div>
            ))
          ) : (
            <p className="text-sm text-slate-500">No recent activities found.</p>
          )}
        </div>
      </motion.div>

      {/* ───────── MODALS ───────── */}
      <AnimatePresence>
        {activeModal && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={closeModal}
              className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-40"
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              className="fixed inset-0 m-auto w-full max-w-lg h-fit max-h-[90vh] bg-white rounded-3xl shadow-2xl z-50 overflow-hidden flex flex-col"
            >
              {/* Modal Header */}
              <div className={`p-6 border-b border-slate-100 flex items-center justify-between ${activeModal === "diagnosis" ? "bg-cyan-50" : "bg-emerald-50"}`}>
                <div className="flex items-center gap-3">
                  <div className={`p-2.5 rounded-xl ${activeModal === "diagnosis" ? "bg-cyan-100 text-cyan-600" : "bg-emerald-100 text-emerald-600"}`}>
                    {activeModal === "diagnosis" ? <Stethoscope className="w-6 h-6" /> : <Pill className="w-6 h-6" />}
                  </div>
                  <div>
                    <h2 className="text-xl font-bold text-slate-800">
                      {activeModal === "diagnosis" ? "New Diagnosis" : "Write Prescription"}
                    </h2>
                    <p className="text-sm text-slate-500">
                      {activeModal === "diagnosis" ? "Record a patient diagnosis" : "Prescribe medication to a patient"}
                    </p>
                  </div>
                </div>
                <button onClick={closeModal} className="p-2 rounded-full hover:bg-slate-200 text-slate-500 transition-colors">
                  <X className="w-5 h-5" />
                </button>
              </div>

              {/* Modal Body */}
              <div className="p-6 overflow-y-auto">
                {submitted ? (
                  <div className="text-center py-12">
                    <CheckCircle className="w-16 h-16 text-emerald-500 mx-auto mb-4" />
                    <h3 className="text-xl font-bold text-slate-800">Successfully Submitted!</h3>
                    <p className="text-sm text-slate-500 mt-2">The record has been securely saved.</p>
                  </div>
                ) : (
                  <form onSubmit={activeModal === "diagnosis" ? handleDiagnosisSubmit : handlePrescriptionSubmit}>
                    {/* Patient Search — shared by both modals */}
                    <div className="mb-6">
                      <PatientSearchSelect
                        searchFn={searchDoctorPatients}
                        onSelect={setSelectedPatient}
                        selectedPatient={selectedPatient}
                        onClear={() => setSelectedPatient(null)}
                        label="Select Patient"
                      />
                    </div>

                    {activeModal === "diagnosis" ? (
                      <div className="space-y-4">
                        <div>
                          <label className="block text-sm font-medium text-slate-700 mb-1">Diagnosis Title *</label>
                          <input type="text" required value={diagTitle} onChange={(e) => setDiagTitle(e.target.value)} className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:ring-2 focus:ring-cyan-500/20 focus:border-cyan-500 outline-none" placeholder="e.g. Acute Bronchitis" />
                        </div>
                        <div>
                          <label className="block text-sm font-medium text-slate-700 mb-1">Symptoms</label>
                          <input type="text" value={diagSymptoms} onChange={(e) => setDiagSymptoms(e.target.value)} className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:ring-2 focus:ring-cyan-500/20 focus:border-cyan-500 outline-none" placeholder="e.g. Persistent cough, mild fever" />
                        </div>
                        <div>
                          <label className="block text-sm font-medium text-slate-700 mb-1">Description</label>
                          <textarea rows={3} value={diagDesc} onChange={(e) => setDiagDesc(e.target.value)} className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:ring-2 focus:ring-cyan-500/20 focus:border-cyan-500 outline-none resize-none" placeholder="Detailed clinical observations..." />
                        </div>
                        <div>
                          <label className="block text-sm font-medium text-slate-700 mb-1">Doctor&apos;s Notes</label>
                          <textarea rows={2} value={diagNotes} onChange={(e) => setDiagNotes(e.target.value)} className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:ring-2 focus:ring-cyan-500/20 focus:border-cyan-500 outline-none resize-none" placeholder="Internal notes..." />
                        </div>
                      </div>
                    ) : (
                      <div className="space-y-4">
                        <div>
                          <label className="block text-sm font-medium text-slate-700 mb-1">Medicine Name *</label>
                          <input type="text" required value={rxMedicine} onChange={(e) => setRxMedicine(e.target.value)} className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 outline-none" placeholder="e.g. Amoxicillin 500mg" />
                        </div>
                        <div className="grid grid-cols-2 gap-4">
                          <div>
                            <label className="block text-sm font-medium text-slate-700 mb-1">Dosage *</label>
                            <input type="text" required value={rxDosage} onChange={(e) => setRxDosage(e.target.value)} className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 outline-none" placeholder="e.g. 500mg" />
                          </div>
                          <div>
                            <label className="block text-sm font-medium text-slate-700 mb-1">Frequency *</label>
                            <input type="text" required value={rxFrequency} onChange={(e) => setRxFrequency(e.target.value)} className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 outline-none" placeholder="e.g. 3x per day" />
                          </div>
                        </div>
                        <div>
                          <label className="block text-sm font-medium text-slate-700 mb-1">Duration *</label>
                          <input type="text" required value={rxDuration} onChange={(e) => setRxDuration(e.target.value)} className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 outline-none" placeholder="e.g. 7 days" />
                        </div>
                        <div>
                          <label className="block text-sm font-medium text-slate-700 mb-1">Instructions</label>
                          <textarea rows={2} value={rxInstructions} onChange={(e) => setRxInstructions(e.target.value)} className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 outline-none resize-none" placeholder="e.g. Take after meals, avoid alcohol" />
                        </div>
                      </div>
                    )}

                    <button
                      type="submit"
                      disabled={!selectedPatient || submitting}
                      className={`w-full mt-6 flex items-center justify-center gap-2 py-3.5 rounded-xl font-bold text-white transition-all disabled:opacity-50 disabled:cursor-not-allowed ${
                        activeModal === "diagnosis"
                          ? "bg-cyan-600 hover:bg-cyan-700 shadow-lg shadow-cyan-600/20"
                          : "bg-emerald-600 hover:bg-emerald-700 shadow-lg shadow-emerald-600/20"
                      }`}
                    >
                      {submitting ? (
                        <>
                          <Loader2 className="w-5 h-5 animate-spin" />
                          Submitting...
                        </>
                      ) : (
                        <>
                          <Plus className="w-5 h-5" />
                          {activeModal === "diagnosis" ? "Submit Diagnosis" : "Submit Prescription"}
                        </>
                      )}
                    </button>
                  </form>
                )}
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
