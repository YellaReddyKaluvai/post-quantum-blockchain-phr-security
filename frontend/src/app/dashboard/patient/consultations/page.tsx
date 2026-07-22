"use client";

import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Stethoscope, Calendar, ChevronDown, ChevronUp, User, Activity, FileText } from "lucide-react";
import { getPatientConsultations } from "@/lib/session";

export default function ConsultationsPage() {
  const [loading, setLoading] = useState(true);
  const [consultations, setConsultations] = useState<any[]>([]);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    async function loadData() {
      try {
        const data = await getPatientConsultations();
        setConsultations(data);
      } catch (error) {
        console.error("Failed to load consultations:", error);
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
        <h1 className="text-xl md:text-2xl font-bold text-slate-800">Consultations</h1>
        <p className="text-slate-500 mt-1">Review your past doctor visits and diagnoses.</p>
      </motion.div>

      {consultations.length === 0 ? (
        <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-12 text-center">
          <Stethoscope className="w-16 h-16 text-slate-200 mx-auto mb-4" />
          <h3 className="text-lg font-bold text-slate-700">No Consultations Found</h3>
          <p className="text-slate-500">You have no consultation history.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {consultations.map((consultation: any, index: number) => {
            const isExpanded = expandedId === consultation.id;
            return (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.1 }}
                key={consultation.id}
                className={`bg-white rounded-2xl shadow-sm border overflow-hidden transition-all duration-300 ${isExpanded ? "border-cyan-200 ring-2 ring-cyan-50" : "border-slate-100 hover:shadow-md"}`}
              >
                {/* Collapsed Header */}
                <div 
                  className="p-5 md:p-6 cursor-pointer flex items-center justify-between gap-4 relative overflow-hidden"
                  onClick={() => setExpandedId(isExpanded ? null : consultation.id)}
                >
                  <div className={`absolute top-0 left-0 w-1.5 h-full ${isExpanded ? "bg-cyan-500" : "bg-slate-200"}`}></div>
                  
                  <div className="flex items-center gap-4 pl-2 flex-1">
                    <div className={`p-3 rounded-xl transition-colors ${isExpanded ? "bg-cyan-100 text-cyan-600" : "bg-slate-50 text-slate-400"}`}>
                      <Stethoscope className="w-6 h-6" />
                    </div>
                    <div>
                      <h3 className="text-lg font-bold text-slate-800 flex items-center gap-2">
                        Dr. {consultation.doctor_name}
                      </h3>
                      <div className="flex flex-wrap items-center gap-3 mt-1 text-sm font-medium text-slate-500">
                        <span className="px-2 py-0.5 bg-slate-100 rounded-md text-slate-600">{consultation.specialization}</span>
                        <span className="flex items-center gap-1.5"><Calendar className="w-4 h-4" /> {new Date(consultation.date).toLocaleDateString()}</span>
                      </div>
                    </div>
                  </div>
                  <div className={`p-2 rounded-full transition-colors ${isExpanded ? "bg-cyan-50 text-cyan-600" : "bg-slate-50 text-slate-400 hover:bg-slate-100"}`}>
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
                      className="border-t border-slate-100 bg-slate-50/50"
                    >
                      <div className="p-5 md:p-6 pl-7 space-y-5">
                        {consultation.symptoms && (
                          <div className="flex gap-4">
                            <Activity className="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5" />
                            <div>
                              <h4 className="text-sm font-bold text-slate-700 uppercase tracking-wide mb-1">Symptoms Reported</h4>
                              <p className="text-sm text-slate-600 bg-white p-3.5 rounded-xl border border-slate-200 shadow-sm">{consultation.symptoms}</p>
                            </div>
                          </div>
                        )}
                        
                        {consultation.diagnosis_summary && (
                          <div className="flex gap-4">
                            <FileText className="w-5 h-5 text-cyan-500 flex-shrink-0 mt-0.5" />
                            <div className="flex-1">
                              <h4 className="text-sm font-bold text-slate-700 uppercase tracking-wide mb-1">Diagnosis Summary</h4>
                              <p className="text-sm text-slate-600 bg-white p-3.5 rounded-xl border border-cyan-100 shadow-sm">{consultation.diagnosis_summary}</p>
                            </div>
                          </div>
                        )}
                        
                        {consultation.doctor_notes && (
                          <div className="flex gap-4">
                            <User className="w-5 h-5 text-emerald-500 flex-shrink-0 mt-0.5" />
                            <div className="flex-1">
                              <h4 className="text-sm font-bold text-slate-700 uppercase tracking-wide mb-1">Doctor's Notes</h4>
                              <p className="text-sm text-slate-600 bg-white p-3.5 rounded-xl border border-emerald-100 shadow-sm whitespace-pre-wrap">{consultation.doctor_notes}</p>
                            </div>
                          </div>
                        )}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            );
          })}
        </div>
      )}
    </div>
  );
}
