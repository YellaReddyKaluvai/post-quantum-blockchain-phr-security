"use client";

import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { FileHeart, ChevronDown, ChevronUp, User, Calendar, Stethoscope } from "lucide-react";
import { getPatientMedicalRecords } from "@/lib/session";

interface MedicalRecordItem {
  id: string;
  title?: string;
  visit_date?: string;
  doctor_name?: string;
  description?: string;
  symptoms?: string;
  doctor_notes?: string;
  // The API returns this as a single string, the way a doctor typed it —
  // typing it as string[] here is what made .map() crash at runtime.
  recommended_tests?: string | null;
}

export default function MedicalRecordsPage() {
  const [loading, setLoading] = useState(true);
  const [records, setRecords] = useState<MedicalRecordItem[]>([]);

  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    async function loadData() {
      try {
        const data = await getPatientMedicalRecords();
        setRecords(data);
      } catch (error) {
        console.error("Failed to load medical records:", error);
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
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="bg-white rounded-2xl h-24 animate-pulse shadow-sm border border-slate-100"></div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-xl md:text-2xl font-bold text-slate-800">Medical Records</h1>
        <p className="text-slate-500 mt-1">Timeline of your visits, diagnoses, and medical history.</p>
      </motion.div>

      {records.length === 0 ? (
        <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-12 text-center">
          <FileHeart className="w-16 h-16 text-slate-200 mx-auto mb-4" />
          <h3 className="text-lg font-bold text-slate-700">No Medical Records Found</h3>
          <p className="text-slate-500">You don&apos;t have any medical records available yet.</p>
        </div>
      ) : (
        <div className="relative border-l-2 border-cyan-100 ml-4 md:ml-6 space-y-6">
          {records.map((record: MedicalRecordItem, index: number) => {
            const isExpanded = expandedId === record.id;
            return (
              <motion.div
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.1 }}
                key={record.id}
                className="relative pl-6 md:pl-8 group"
              >
                {/* Timeline Node */}
                <div className={`absolute -left-[9px] top-6 w-4 h-4 rounded-full border-2 bg-white transition-all ${isExpanded ? "border-cyan-500 ring-4 ring-cyan-100 scale-110" : "border-slate-300 group-hover:border-cyan-400"}`}></div>

                {/* Card Container */}
                <div className={`bg-white rounded-2xl shadow-sm border overflow-hidden transition-all duration-300 ${isExpanded ? "border-cyan-200 ring-2 ring-cyan-50 shadow-md" : "border-slate-100 hover:border-slate-200 hover:shadow-md"}`}>
                  
                  {/* Collapsed Header */}
                  <div 
                    className="p-5 md:p-6 cursor-pointer flex flex-col md:flex-row md:items-center justify-between gap-4"
                    onClick={() => setExpandedId(isExpanded ? null : record.id)}
                  >
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <h3 className="text-lg font-bold text-slate-800">{record.title}</h3>
                      </div>
                      <div className="flex flex-wrap items-center gap-4 text-sm text-slate-500 font-medium">
                        <span className="flex items-center gap-1.5"><Calendar className="w-4 h-4 text-slate-400" /> {new Date(record.visit_date || Date.now()).toLocaleDateString()}</span>
                        <span className="flex items-center gap-1.5"><User className="w-4 h-4 text-slate-400" /> Dr. {record.doctor_name}</span>
                      </div>
                    </div>

                    <div className="flex items-center justify-between md:justify-end gap-3 pt-3 md:pt-0 border-t md:border-t-0 border-slate-100">
                      <span className="text-xs font-semibold text-cyan-600 bg-cyan-50 px-3 py-1 rounded-full">Diagnosis Record</span>
                      <div className={`p-2 rounded-full transition-colors ${isExpanded ? "bg-cyan-100 text-cyan-600" : "bg-slate-50 text-slate-400 group-hover:bg-slate-100"}`}>
                        {isExpanded ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
                      </div>
                    </div>
                  </div>

                  {/* Expanded Details */}
                  <AnimatePresence>
                    {isExpanded && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        className="border-t border-slate-100 bg-slate-50/50"
                      >
                        <div className="p-5 md:p-6 space-y-4">
                          {record.description && (
                            <div>
                              <h4 className="text-sm font-semibold text-slate-700 mb-1">Clinical Overview</h4>
                              <p className="text-sm text-slate-600 leading-relaxed bg-white p-3.5 rounded-xl border border-slate-100">{record.description}</p>
                            </div>
                          )}

                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            {record.symptoms && (
                              <div>
                                <h4 className="text-sm font-semibold text-slate-700 mb-1">Symptoms</h4>
                                <p className="text-sm text-slate-600 bg-white p-3 rounded-lg border border-slate-100">{record.symptoms}</p>
                              </div>
                            )}
                            
                            {record.doctor_notes && (
                              <div>
                                <h4 className="text-sm font-semibold text-slate-700 flex items-center gap-2 mb-1">
                                  <Stethoscope className="w-4 h-4 text-emerald-500" /> Doctor&apos;s Notes
                                </h4>
                                <p className="text-sm text-slate-600 bg-white p-3 rounded-lg border border-slate-100">{record.doctor_notes}</p>
                              </div>
                            )}
                          </div>


                          {record.recommended_tests && record.recommended_tests.trim().length > 0 && (
                            <div>
                              <h4 className="text-sm font-semibold text-slate-700 mb-2">Recommended Tests</h4>
                              <div className="flex flex-wrap gap-2">
                                {record.recommended_tests
                                  .split(",")
                                  .map((test) => test.trim())
                                  .filter(Boolean)
                                  .map((test: string, i: number) => (
                                    <span key={i} className="px-3 py-1 bg-white border border-slate-200 rounded-full text-xs font-medium text-slate-600">
                                      {test}
                                    </span>
                                  ))}
                              </div>
                            </div>
                          )}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              </motion.div>
            );
          })}
        </div>
      )}
    </div>
  );
}
