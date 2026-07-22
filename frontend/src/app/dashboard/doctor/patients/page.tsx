"use client";

import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Users, User, ArrowRight } from "lucide-react";
import Link from "next/link";
import { getDoctorPatients } from "@/lib/session";

export default function MyPatients() {
  const [patients, setPatients] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchPatients() {
      try {
        const data = await getDoctorPatients();
        setPatients(data);
      } catch (error) {
        console.error("Error fetching patients:", error);
      } finally {
        setLoading(false);
      }
    }
    fetchPatients();
  }, []);

  if (loading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
        {[1, 2, 3, 4, 5, 6].map((i) => (
          <div key={i} className="h-48 bg-slate-200 animate-pulse rounded-2xl" />
        ))}
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <div className="flex items-center gap-3 mb-6">
        <Users className="w-6 h-6 text-cyan-600" />
        <h1 className="text-2xl font-bold text-slate-800">My Patients</h1>
      </div>

      {patients.length === 0 ? (
        <div className="text-center py-12 bg-white rounded-2xl shadow-sm border border-slate-100">
          <p className="text-slate-500">No patients assigned yet.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {patients.map((patient, i) => (
            <motion.div
              key={patient.id || i}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
              className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100 hover:shadow-md transition-shadow"
            >
              <div className="flex items-center gap-4 mb-4">
                <div className="w-12 h-12 rounded-full bg-cyan-100 flex items-center justify-center">
                  <User className="w-6 h-6 text-cyan-600" />
                </div>
                <div>
                  <h3 className="font-bold text-slate-800">{patient.name || "Unknown Patient"}</h3>
                  <p className="text-xs text-slate-500">{patient.email || "No email"}</p>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4 mb-6">
                <div>
                  <p className="text-xs text-slate-400">Gender</p>
                  <p className="text-sm font-medium text-slate-700">{patient.gender || "N/A"}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-400">Blood Group</p>
                  <p className="text-sm font-medium text-slate-700">{patient.blood_group || "N/A"}</p>
                </div>
                <div className="col-span-2">
                  <p className="text-xs text-slate-400">Last Visit</p>
                  <p className="text-sm font-medium text-slate-700">
                    {patient.last_visit ? new Date(patient.last_visit).toLocaleDateString() : "Never"}
                  </p>
                </div>
              </div>
              <Link
                href={`/dashboard/doctor/patients/${patient.id}`}
                className="w-full flex items-center justify-center gap-2 py-2 px-4 bg-slate-50 hover:bg-slate-100 text-slate-700 rounded-xl font-semibold text-sm transition-colors"
              >
                View Details
                <ArrowRight className="w-4 h-4" />
              </Link>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
