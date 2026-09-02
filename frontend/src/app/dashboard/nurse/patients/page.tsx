"use client";

import React, { useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import { Search, User, Droplet, ClipboardPlus } from "lucide-react";
import Link from "next/link";
import { getNursePatients, searchNursePatients } from "@/lib/session";

interface NursePatientItem {
  id: string;
  user_id?: string;
  full_name: string;
  gender: string;
  blood_group?: string | null;
  last_recorded_at?: string | null;
  status?: string;
}

export default function NursePatientsPage() {
  const [searchTerm, setSearchTerm] = useState("");
  const [myPatients, setMyPatients] = useState<NursePatientItem[]>([]);
  const [searchResults, setSearchResults] = useState<NursePatientItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);

  useEffect(() => {
    getNursePatients()
      .then((data) => setMyPatients(data))
      .catch((err) => console.error("Failed to load my patients:", err))
      .finally(() => setLoading(false));
  }, []);

  const handleSearch = useCallback(async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (searchTerm.trim().length < 2) {
      setSearchResults(null);
      return;
    }
    setSearching(true);
    try {
      const data = await searchNursePatients(searchTerm.trim());
      setSearchResults(data);
    } catch (error) {
      console.error("Search failed:", error);
      setSearchResults([]);
    } finally {
      setSearching(false);
    }
  }, [searchTerm]);

  useEffect(() => {
    const timer = setTimeout(() => handleSearch(), 350);
    return () => clearTimeout(timer);
  }, [handleSearch]);

  const displayList = searchResults !== null ? searchResults : myPatients;
  const isSearchMode = searchResults !== null;

  const PatientCard = ({ patient, idx }: { patient: NursePatientItem; idx: number }) => (
    <motion.div
      key={patient.id}
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ delay: idx * 0.04 }}
      className="bg-white/80 backdrop-blur-md rounded-2xl shadow-sm border border-slate-100 overflow-hidden flex flex-col"
    >
      <div className="p-6 flex-1">
        <div className="flex justify-between items-start mb-4">
          <div>
            <h3 className="text-lg font-bold text-slate-800">{patient.full_name}</h3>
            <p className="text-xs font-semibold text-slate-500">{patient.user_id}</p>
          </div>
          <div className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center">
            <User className="w-5 h-5 text-slate-500" />
          </div>
        </div>
        <div className="space-y-2 mb-2">
          <div className="flex items-center gap-2 text-sm text-slate-600">
            <User className="w-4 h-4 text-slate-400" />
            <span>{patient.gender}</span>
          </div>
          {patient.blood_group && (
            <div className="flex items-center gap-2 text-sm text-slate-600">
              <Droplet className="w-4 h-4 text-rose-400" />
              <span>Blood Group: <span className="font-semibold text-slate-800">{patient.blood_group}</span></span>
            </div>
          )}
          {!isSearchMode && patient.last_recorded_at && (
            <p className="text-xs text-slate-400 mt-1">Last attended: {new Date(patient.last_recorded_at).toLocaleString()}</p>
          )}
        </div>
      </div>
      <div className="p-4 border-t border-slate-100 bg-slate-50/50">
        <Link
          href={`/dashboard/nurse/patients/${patient.id}`}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-cyan-600 hover:bg-cyan-700 text-white rounded-lg text-xs font-semibold transition-colors"
        >
          <ClipboardPlus className="w-4 h-4" />
          Open Chart
        </Link>
      </div>
    </motion.div>
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Patient Directory</h1>
        <p className="text-sm text-slate-500">Search any patient, or open a chart you&apos;ve recently attended to.</p>
      </div>

      <div className="bg-white/80 backdrop-blur-md rounded-2xl shadow-sm border border-slate-100 p-6">
        <form onSubmit={handleSearch} className="flex gap-4 max-w-2xl">
          <div className="relative flex-1">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
            <input
              type="text"
              placeholder="Search by patient name or ID..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-12 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500/20 focus:border-cyan-500 transition-all"
            />
          </div>
        </form>
      </div>

      <h2 className="text-sm font-bold text-slate-500 uppercase tracking-wide">
        {isSearchMode ? "Search Results" : "My Recently Attended Patients"}
      </h2>

      {loading || searching ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
          {[1, 2, 3].map((i) => (
            <div key={i} className="bg-white rounded-2xl shadow-sm border border-slate-100 p-6 animate-pulse h-48" />
          ))}
        </div>
      ) : displayList.length === 0 ? (
        <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-12 text-center">
          <User className="w-16 h-16 mx-auto text-slate-300 mb-4" />
          <h3 className="text-lg font-bold text-slate-700">
            {isSearchMode ? "No Patients Found" : "No Patients Attended Yet"}
          </h3>
          <p className="text-slate-500 mt-1">
            {isSearchMode ? "Try a different name or ID." : "Search above to open a patient's chart and record vitals or notes."}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
          {displayList.map((patient, idx) => (
            <PatientCard key={patient.id} patient={patient} idx={idx} />
          ))}
        </div>
      )}
    </div>
  );
}
