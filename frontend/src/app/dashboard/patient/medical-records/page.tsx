"use client";

import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { FileHeart, ChevronDown, ChevronUp, User, Calendar, Stethoscope } from "lucide-react";
import { getPatientMedicalRecords } from "@/lib/session";

export default function MedicalRecordsPage() {
  const [loading, setLoading] = useState(true);
  const [records, setRecords] = useState<any[]>([]);
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
          <p className="text-slate-500">You don't have any medical records available yet.</p>
        </div>
      ) : (
        <div className="relative border-l-2 border-cyan-100 ml-4 md:ml-6 space-y-6">
          {records.map((record: any, index: number) => {
            const isExpanded = expandedId === record.id;
            return (
              <motion.div
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.1 }}
                key={record.id || index}
                className="relative pl-6 md:pl-8"
              >
                {/* Timeline Dot */}
                <div className="absolute -left-[9px] top-6 w-4 h-4 rounded-full bg-cyan-400 border-4 border-white shadow-sm"></div>

                <div className={`bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden transition-all duration-300 ${isExpanded ? "ring-2 ring-cyan-100" : "hover:shadow-md"}`}>
                  {/* Collapsed Header */}
                  <div 
                    className="p-4 md:p-6 cursor-pointer flex items-center justify-between gap-4"
                    onClick={() => setExpandedId(isExpanded ? null : record.id)}
                  >
                    <div className="flex-1">
                      <h3 className="text-lg font-bold text-slate-800">{record.title}</h3>
                      <div className="flex flex-wrap items-center gap-4 mt-2 text-sm text-slate-500">
                        <span className="flex items-center gap-1.5"><Calendar className="w-4 h-4" /> {new Date(record.visit_date).toLocaleDateString()}</span>
                        <span className="flex items-center gap-1.5"><User className="w-4 h-4" /> Dr. {record.doctor_name}</span>
                      </div>
                    </div>
                    <div className="p-2 bg-slate-50 rounded-full text-slate-400 hover:bg-slate-100 transition-colors">
                      {isExpanded ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
                    </div>
                  </div>

                  {/* Expanded Content */}
                  <AnimatePresence>
                    {isExpanded && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        className="border-t border-slate-100"
                      >
                        <div className="p-4 md:p-6 bg-slate-50/50 space-y-4">
                          {record.description && (
                            <div>
                              <h4 className="text-sm font-semibold text-slate-700 flex items-center gap-2 mb-1">
                                <FileHeart className="w-4 h-4 text-cyan-500" /> Description
                              </h4>
                              <p className="text-sm text-slate-600 bg-white p-3 rounded-lg border border-slate-100">{record.description}</p>
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
                                  <Stethoscope className="w-4 h-4 text-emerald-500" /> Doctor's Notes
                                </h4>
                                <p className="text-sm text-slate-600 bg-white p-3 rounded-lg border border-slate-100">{record.doctor_notes}</p>
                              </div>
                            )}
                          </div>

                          {record.recommended_tests && record.recommended_tests.length > 0 && (
                            <div>
                              <h4 className="text-sm font-semibold text-slate-700 mb-2">Recommended Tests</h4>
                              <div className="flex flex-wrap gap-2">
                                {record.recommended_tests.map((test: string, i: number) => (
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
