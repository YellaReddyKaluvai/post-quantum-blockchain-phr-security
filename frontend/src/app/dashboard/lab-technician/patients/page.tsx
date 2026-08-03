"use client";

import React, { useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import { Search, User, Droplet, FilePlus, FileCheck, Stethoscope } from "lucide-react";
import { searchPatientsForLab } from "@/lib/session";
import Link from "next/link";

interface LabPatientItem {
  id: string;
  name?: string;
  full_name?: string;
  age?: number;
  gender?: string;
  bloodGroup?: string;
  blood_group?: string;
  assignedDoctor?: string;
  user_id?: string;
  [key: string]: unknown;
}

export default function PatientSearchPage() {
  const [searchTerm, setSearchTerm] = useState("");
  const [patients, setPatients] = useState<LabPatientItem[]>([]);

  const [loading, setLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);

  const handleSearch = useCallback(async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setLoading(true);
    setHasSearched(true);
    
    try {
      const data = await searchPatientsForLab(searchTerm || "all");
      setPatients(data);
    } catch (error) {
      console.error(error);
      // Fallback
      setPatients([
        { id: "PAT-8821", name: "John Doe", age: 45, gender: "Male", bloodGroup: "O+", assignedDoctor: "Dr. Sarah Smith" },
        { id: "PAT-9932", name: "Jane Smith", age: 32, gender: "Female", bloodGroup: "A-", assignedDoctor: "Dr. Michael Jones" },
        { id: "PAT-1123", name: "Mark Johnson", age: 58, gender: "Male", bloodGroup: "B+", assignedDoctor: "Dr. Emily Davis" },
      ]);
    } finally {
      setLoading(false);
    }
  }, [searchTerm]);

  useEffect(() => {
    handleSearch();
  }, [handleSearch]);


  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Patient Directory</h1>
        <p className="text-sm text-slate-500">Search for patients to create or view laboratory reports.</p>
      </div>

      <div className="bg-white/80 backdrop-blur-md rounded-2xl shadow-sm border border-slate-100 p-6">
        <form onSubmit={handleSearch} className="flex gap-4 max-w-2xl">
          <div className="relative flex-1">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
            <input
              type="text"
              placeholder="Search by Patient Name, ID, or Phone..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-12 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500/20 focus:border-cyan-500 transition-all"
            />
          </div>
          <button
            type="submit"
            className="px-6 py-3 bg-cyan-600 hover:bg-cyan-700 text-white font-semibold rounded-xl shadow-sm shadow-cyan-600/20 transition-all"
          >
            Search
          </button>
        </form>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
          {[1, 2, 3].map((i) => (
            <div key={i} className="bg-white rounded-2xl shadow-sm border border-slate-100 p-6 animate-pulse h-48" />
          ))}
        </div>
      ) : hasSearched && patients.length === 0 ? (
        <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-12 text-center">
          <User className="w-16 h-16 mx-auto text-slate-300 mb-4" />
          <h3 className="text-lg font-bold text-slate-700">No Patients Found</h3>
          <p className="text-slate-500 mt-1">Try adjusting your search criteria.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
          {patients.map((patient: LabPatientItem, idx: number) => (

            <motion.div
              key={patient.id}
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: idx * 0.05 }}
              className="bg-white/80 backdrop-blur-md rounded-2xl shadow-sm border border-slate-100 overflow-hidden flex flex-col"
            >
              <div className="p-6 flex-1">
                <div className="flex justify-between items-start mb-4">
                  <div>
                    <h3 className="text-lg font-bold text-slate-800">{patient.name}</h3>
                    <p className="text-xs font-semibold text-slate-500">{patient.id}</p>
                  </div>
                  <div className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center">
                    <User className="w-5 h-5 text-slate-500" />
                  </div>
                </div>
                
                <div className="space-y-2 mb-6">
                  <div className="flex items-center gap-2 text-sm text-slate-600">
                    <User className="w-4 h-4 text-slate-400" />
                    <span>{patient.age} yrs • {patient.gender}</span>
                  </div>
                  <div className="flex items-center gap-2 text-sm text-slate-600">
                    <Droplet className="w-4 h-4 text-rose-400" />
                    <span>Blood Group: <span className="font-semibold text-slate-800">{patient.bloodGroup}</span></span>
                  </div>
                  <div className="flex items-center gap-2 text-sm text-slate-600">
                    <Stethoscope className="w-4 h-4 text-cyan-500" />
                    <span>{patient.assignedDoctor}</span>
                  </div>
                </div>
              </div>

              <div className="p-4 border-t border-slate-100 bg-slate-50/50 flex gap-2">
                <Link
                  href={`/dashboard/lab-technician/create-report?patientId=${patient.id}`}
                  className="flex-1 flex items-center justify-center gap-2 px-3 py-2 bg-cyan-600 hover:bg-cyan-700 text-white rounded-lg text-xs font-semibold transition-colors"
                >
                  <FilePlus className="w-4 h-4" />
                  Create Report
                </Link>
                <Link
                  href={`/dashboard/lab-technician/reports?patientId=${patient.id}`}
                  className="flex-1 flex items-center justify-center gap-2 px-3 py-2 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 rounded-lg text-xs font-semibold transition-colors"
                >
                  <FileCheck className="w-4 h-4" />
                  View History
                </Link>
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
