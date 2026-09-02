"use client";

import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Pill, User, Calendar, Clock, AlertCircle, Activity } from "lucide-react";
import { getPatientPrescriptions } from "@/lib/session";

// Mirrors the backend PrescriptionRecord exactly.
interface PrescriptionItem {
  id: string;
  medicine_name?: string;
  dosage?: string;
  frequency?: string;
  duration?: string;
  instructions?: string;
  prescribed_date?: string | null;
  doctor_name?: string | null;
}

export default function PrescriptionsPage() {
  const [loading, setLoading] = useState(true);
  const [prescriptions, setPrescriptions] = useState<PrescriptionItem[]>([]);


  useEffect(() => {
    async function loadData() {
      try {
        const data = await getPatientPrescriptions();
        setPrescriptions(data);
      } catch (error) {
        console.error("Failed to load prescriptions:", error);
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
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3].map((i) => (
            <div key={i} className="bg-white rounded-2xl p-6 h-64 animate-pulse shadow-sm border border-slate-100"></div>
          ))}
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

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-xl md:text-2xl font-bold text-slate-800">Prescriptions</h1>
        <p className="text-slate-500 mt-1">Manage your prescribed medications and instructions.</p>
      </motion.div>

      {prescriptions.length === 0 ? (
        <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-12 text-center">
          <Pill className="w-16 h-16 text-slate-200 mx-auto mb-4" />
          <h3 className="text-lg font-bold text-slate-700">No Prescriptions Found</h3>
          <p className="text-slate-500">You do not have any active or past prescriptions.</p>
        </div>
      ) : (
        <motion.div
          variants={containerVariants}
          initial="hidden"
          animate="show"
          className="grid grid-cols-1 lg:grid-cols-2 gap-6"
        >
          {prescriptions.map((prescription: PrescriptionItem) => (
            <motion.div
              key={prescription.id}
              variants={{ hidden: { opacity: 0, y: 20 }, show: { opacity: 1, y: 0 } }}
              className="bg-white rounded-2xl shadow-sm border border-slate-100 p-6 flex flex-col sm:flex-row gap-6 relative overflow-hidden group hover:shadow-lg transition-shadow"
            >
              <div className="absolute top-0 left-0 w-1 h-full bg-gradient-to-b from-teal-400 to-cyan-500"></div>
              
              <div className="flex-shrink-0 flex sm:flex-col items-center justify-between sm:justify-start gap-4 sm:w-32 border-b sm:border-b-0 sm:border-r border-slate-100 pb-4 sm:pb-0 sm:pr-6">
                <div className="p-4 bg-teal-50 text-teal-600 rounded-2xl group-hover:scale-110 transition-transform shadow-sm">
                  <Pill className="w-8 h-8" />
                </div>
                <div className="text-right sm:text-center">
                  <span className="block text-xs font-bold text-slate-400 uppercase tracking-wide">Prescribed on</span>
                  <span className="text-sm font-semibold text-slate-700">{prescription.prescribed_date ? new Date(prescription.prescribed_date).toLocaleDateString() : "—"}</span>
                </div>
              </div>

              <div className="flex-1 space-y-4">
                <div>
                  <h3 className="text-xl font-bold text-slate-800">{prescription.medicine_name}</h3>
                  <div className="flex items-center gap-2 mt-1 text-sm text-slate-500 font-medium">
                    <User className="w-4 h-4" /> Dr. {prescription.doctor_name || "—"}
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4 bg-slate-50 rounded-xl p-4 border border-slate-100">
                  <div>
                    <span className="text-xs text-slate-500 block mb-1 flex items-center gap-1"><Activity className="w-3 h-3" /> Dosage</span>
                    <span className="font-semibold text-slate-800 text-sm">{prescription.dosage}</span>
                  </div>
                  <div>
                    <span className="text-xs text-slate-500 block mb-1 flex items-center gap-1"><Clock className="w-3 h-3" /> Frequency</span>
                    <span className="font-semibold text-slate-800 text-sm">{prescription.frequency}</span>
                  </div>
                  <div className="col-span-2">
                    <span className="text-xs text-slate-500 block mb-1 flex items-center gap-1"><Calendar className="w-3 h-3" /> Duration</span>
                    <span className="font-semibold text-slate-800 text-sm">{prescription.duration}</span>
                  </div>
                </div>

                {prescription.instructions && (
                  <div className="bg-amber-50 rounded-xl p-4 border border-amber-100 flex gap-3">
                    <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
                    <div>
                      <span className="block text-xs font-bold text-amber-800 uppercase tracking-wide mb-1">Instructions</span>
                      <p className="text-sm text-amber-900">{prescription.instructions}</p>
                    </div>
                  </div>
                )}
              </div>
            </motion.div>
          ))}
        </motion.div>
      )}
    </div>
  );
}
