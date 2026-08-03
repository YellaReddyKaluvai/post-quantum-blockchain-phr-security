"use client";

import React, { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { motion } from "framer-motion";
import { User, Activity, FileText, ChevronLeft, Plus, X } from "lucide-react";
import Link from "next/link";
import { getDoctorPatientDetail, createDiagnosis, createPrescription } from "@/lib/session";

interface PatientDetailInfo {
  id: string;
  name?: string;
  email?: string;
  gender?: string;
  blood_group?: string;
  date_of_birth?: string;
  dob?: string;
  diagnoses?: Record<string, unknown>[];
  prescriptions?: Record<string, unknown>[];
  [key: string]: unknown;
}


export default function PatientDetails() {
  const params = useParams();
  const [patient, setPatient] = useState<PatientDetailInfo | null>(null);

  const [loading, setLoading] = useState(true);


  const [diagnosisModal, setDiagnosisModal] = useState(false);
  const [prescriptionModal, setPrescriptionModal] = useState(false);
  const [formData, setFormData] = useState({ description: "", medications: "" });

  useEffect(() => {
    async function fetchDetail() {
      try {
        const data = await getDoctorPatientDetail(params.id as string);
        setPatient(data);
      } catch (error) {
        console.error("Error fetching patient detail:", error);
      } finally {
        setLoading(false);
      }
    }
    fetchDetail();
  }, [params.id]);

  const handleDiagnosis = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await createDiagnosis(params.id as string, { description: formData.description });
      setDiagnosisModal(false);
      setFormData({ ...formData, description: "" });
      // Refresh logic would go here
    } catch (error) {
      console.error(error);
    }
  };

  const handlePrescription = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await createPrescription(params.id as string, { medications: formData.medications });
      setPrescriptionModal(false);
      setFormData({ ...formData, medications: "" });
      // Refresh logic would go here
    } catch (error) {
      console.error(error);
    }
  };

  if (loading) {
    return <div className="h-96 bg-slate-200 animate-pulse rounded-2xl" />;
  }

  if (!patient) {
    return <div className="text-center p-6 text-slate-500">Patient not found.</div>;
  }

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <Link href="/dashboard/doctor/patients" className="flex items-center gap-2 text-slate-500 hover:text-slate-800 transition-colors">
        <ChevronLeft className="w-4 h-4" />
        Back to Patients
      </Link>

      {/* Top Section */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100 flex flex-col md:flex-row gap-6 items-center md:items-start">
        <div className="w-24 h-24 rounded-full bg-cyan-100 flex items-center justify-center flex-shrink-0">
          <User className="w-10 h-10 text-cyan-600" />
        </div>
        <div className="flex-1 grid grid-cols-2 md:grid-cols-4 gap-4 w-full">
          <div>
            <p className="text-xs text-slate-400 uppercase tracking-wider">Name</p>
            <p className="text-lg font-bold text-slate-800">{patient.name || "Unknown"}</p>
          </div>
          <div>
            <p className="text-xs text-slate-400 uppercase tracking-wider">Email</p>
            <p className="text-sm font-medium text-slate-700">{patient.email || "N/A"}</p>
          </div>
          <div>
            <p className="text-xs text-slate-400 uppercase tracking-wider">Gender</p>
            <p className="text-sm font-medium text-slate-700">{patient.gender || "N/A"}</p>
          </div>
          <div>
            <p className="text-xs text-slate-400 uppercase tracking-wider">Blood Group</p>
            <p className="text-sm font-medium text-slate-700">{patient.blood_group || "N/A"}</p>
          </div>
          <div>
            <p className="text-xs text-slate-400 uppercase tracking-wider">DOB</p>
            <p className="text-sm font-medium text-slate-700">{patient.dob || "N/A"}</p>
          </div>
        </div>
        <div className="flex flex-col gap-2 w-full md:w-auto">
          <button onClick={() => setDiagnosisModal(true)} className="flex items-center justify-center gap-2 px-4 py-2 bg-cyan-600 hover:bg-cyan-700 text-white rounded-xl text-sm font-bold transition-colors">
            <Plus className="w-4 h-4" /> New Diagnosis
          </button>
          <button onClick={() => setPrescriptionModal(true)} className="flex items-center justify-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-sm font-bold transition-colors">
            <Plus className="w-4 h-4" /> New Prescription
          </button>
        </div>
      </motion.div>

      {/* Middle Section */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="bg-white rounded-2xl shadow-sm border border-slate-100 p-6">
          <div className="flex items-center gap-3 mb-6 border-b border-slate-100 pb-4">
            <Activity className="w-5 h-5 text-indigo-500" />
            <h2 className="text-lg font-bold text-slate-800">Previous Diagnoses</h2>
          </div>
          <div className="space-y-4">
            {patient.diagnoses && (patient.diagnoses as Record<string, unknown>[]).length > 0 ? (
              (patient.diagnoses as Record<string, unknown>[]).map((d: Record<string, unknown>, i: number) => (
                <div key={i} className="p-4 bg-slate-50 rounded-xl border border-slate-100">
                  <p className="text-sm text-slate-700">{d.description as string}</p>
                  <p className="text-xs text-slate-400 mt-2">{new Date(d.date as string).toLocaleString()}</p>
                </div>
              ))
            ) : (
              <p className="text-sm text-slate-500">No diagnoses recorded.</p>
            )}
          </div>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="bg-white rounded-2xl shadow-sm border border-slate-100 p-6">
          <div className="flex items-center gap-3 mb-6 border-b border-slate-100 pb-4">
            <FileText className="w-5 h-5 text-amber-500" />
            <h2 className="text-lg font-bold text-slate-800">Previous Prescriptions</h2>
          </div>
          <div className="space-y-4">
            {patient.prescriptions && (patient.prescriptions as Record<string, unknown>[]).length > 0 ? (
              (patient.prescriptions as Record<string, unknown>[]).map((p: Record<string, unknown>, i: number) => (
                <div key={i} className="p-4 bg-slate-50 rounded-xl border border-slate-100">
                  <p className="text-sm text-slate-700">{p.medications as string}</p>
                  <p className="text-xs text-slate-400 mt-2">{new Date(p.date as string).toLocaleString()}</p>
                </div>
              ))
            ) : (
              <p className="text-sm text-slate-500">No prescriptions recorded.</p>
            )}
          </div>
        </motion.div>
      </div>

      {/* Modals */}
      {diagnosisModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-bold">New Diagnosis</h3>
              <button onClick={() => setDiagnosisModal(false)}><X className="w-5 h-5 text-slate-500" /></button>
            </div>
            <form onSubmit={handleDiagnosis}>
              <textarea
                required
                className="w-full border border-slate-200 rounded-xl p-3 mb-4 focus:ring-2 focus:ring-cyan-500 outline-none"
                rows={4}
                placeholder="Enter diagnosis details..."
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              />
              <button type="submit" className="w-full bg-cyan-600 text-white rounded-xl py-2 font-bold hover:bg-cyan-700">Submit</button>
            </form>
          </div>
        </div>
      )}

      {prescriptionModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-bold">New Prescription</h3>
              <button onClick={() => setPrescriptionModal(false)}><X className="w-5 h-5 text-slate-500" /></button>
            </div>
            <form onSubmit={handlePrescription}>
              <textarea
                required
                className="w-full border border-slate-200 rounded-xl p-3 mb-4 focus:ring-2 focus:ring-emerald-500 outline-none"
                rows={4}
                placeholder="Enter medications (e.g. Paracetamol 500mg, 1x/day)"
                value={formData.medications}
                onChange={(e) => setFormData({ ...formData, medications: e.target.value })}
              />
              <button type="submit" className="w-full bg-emerald-600 text-white rounded-xl py-2 font-bold hover:bg-emerald-700">Submit</button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
