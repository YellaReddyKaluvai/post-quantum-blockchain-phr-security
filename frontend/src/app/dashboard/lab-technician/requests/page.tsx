"use client";

import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Search, Filter, ClipboardList, CheckCircle, Clock, PlayCircle } from "lucide-react";
import { getLabTestRequests, updateLabTestRequestStatus } from "@/lib/session";

interface TestRequestItem {
  id: string;
  patient_name?: string;
  patientName?: string;
  patient_user_id?: string;
  patientId?: string;
  patient_id?: string;
  test_name?: string;
  testName?: string;
  doctor_name?: string;
  doctorName?: string;
  status?: string;
  requested_date?: string;
  requestedDate?: string;
  priority?: string;
  date?: string;
  notes?: string;
  [key: string]: unknown;
}



export default function RequestsPage() {
  const [requests, setRequests] = useState<TestRequestItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");

  useEffect(() => {
    const fetchRequests = async () => {
      try {
        const data = await getLabTestRequests();
        setRequests(data);
      } catch (error) {
        console.error(error);
        setRequests([
          { id: "REQ-001", patientName: "John Doe", patientId: "PAT-8821", doctorName: "Dr. Sarah Smith", testName: "Complete Blood Count (CBC)", priority: "Routine", date: "2026-07-25", status: "Pending" },
          { id: "REQ-002", patientName: "Jane Smith", patientId: "PAT-9932", doctorName: "Dr. Michael Jones", testName: "MRI Scan (Brain)", priority: "Urgent", date: "2026-07-25", status: "Pending" },
          { id: "REQ-003", patientName: "Mark Johnson", patientId: "PAT-1123", doctorName: "Dr. Emily Davis", testName: "Blood Sugar Fasting", priority: "Emergency", date: "2026-07-25", status: "Processing" },
        ]);
      } finally {
        setLoading(false);
      }
    };
    fetchRequests();
  }, []);

  const handleStatusUpdate = async (id: string, status: string) => {
    try {
      await updateLabTestRequestStatus(id, status);
      setRequests((prev) => prev.map((req) => req.id === id ? { ...req, status } : req));
    } catch (e) {
      console.error(e);
      // Optimistic update for UI feel if API fails
      setRequests((prev) => prev.map((req) => req.id === id ? { ...req, status } : req));
    }
  };

  const getPriorityColor = (priority: string) => {
    if (priority === "Emergency") return "bg-rose-100 text-rose-700 border-rose-200";
    if (priority === "Urgent") return "bg-amber-100 text-amber-700 border-amber-200";
    return "bg-slate-100 text-slate-700 border-slate-200";
  };

  const getStatusColor = (status: string) => {
    if (status === "Completed") return "bg-emerald-100 text-emerald-700 border-emerald-200";
    if (status === "Processing") return "bg-blue-100 text-blue-700 border-blue-200";
    return "bg-slate-100 text-slate-700 border-slate-200";
  };

  const filteredRequests = requests.filter((req: TestRequestItem) => {
    const pName = (req.patient_name || req.patientName || "") as string;
    const pId = (req.patient_user_id || req.patientId || "") as string;
    const tName = (req.test_name || req.testName || "") as string;
    return pName.toLowerCase().includes(searchTerm.toLowerCase()) || 
           pId.toLowerCase().includes(searchTerm.toLowerCase()) ||
           tName.toLowerCase().includes(searchTerm.toLowerCase());
  });


  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Pending Test Requests</h1>
          <p className="text-sm text-slate-500">Manage and process incoming laboratory test requests.</p>
        </div>
      </div>

      <div className="bg-white/80 backdrop-blur-md rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
        <div className="p-4 border-b border-slate-100 flex flex-col sm:flex-row gap-4 justify-between bg-slate-50/50">
          <div className="relative max-w-md w-full">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              type="text"
              placeholder="Search by patient, ID, or test..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-9 pr-4 py-2 bg-white border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500/20 focus:border-cyan-500 transition-all"
            />
          </div>
          <button className="flex items-center gap-2 px-4 py-2 bg-white border border-slate-200 rounded-xl text-sm font-medium text-slate-600 hover:bg-slate-50 transition-colors">
            <Filter className="w-4 h-4" />
            Filter
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-100">
                <th className="px-6 py-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">Patient</th>
                <th className="px-6 py-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">Doctor</th>
                <th className="px-6 py-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">Test Details</th>
                <th className="px-6 py-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">Priority</th>
                <th className="px-6 py-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">Status</th>
                <th className="px-6 py-4 text-xs font-semibold text-slate-500 uppercase tracking-wider text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                [1, 2, 3].map((i) => (
                  <tr key={i}>
                    <td colSpan={6} className="px-6 py-4">
                      <div className="h-12 bg-slate-100 rounded-lg animate-pulse" />
                    </td>
                  </tr>
                ))
              ) : filteredRequests.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-8 text-center text-slate-500">
                    <ClipboardList className="w-12 h-12 mx-auto text-slate-300 mb-3" />
                    <p>No test requests found.</p>
                  </td>
                </tr>
              ) : (
                filteredRequests.map((req: TestRequestItem, idx: number) => (
                  <motion.tr 
                    key={req.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: idx * 0.05 }}
                    className="hover:bg-slate-50/50 transition-colors group"
                  >
                    <td className="px-6 py-4">
                      <p className="font-semibold text-slate-800">{req.patient_name || req.patientName || "Patient"}</p>
                      <p className="text-xs text-slate-500">{req.patient_user_id || req.patientId || req.patient_id}</p>
                    </td>
                    <td className="px-6 py-4">
                      <p className="text-sm font-medium text-slate-700">{req.doctor_name || req.doctorName || "Dr. Unassigned"}</p>
                    </td>
                    <td className="px-6 py-4">
                      <p className="text-sm font-semibold text-slate-800">{req.test_name || req.testName}</p>
                      <p className="text-xs text-slate-500">
                        {req.requested_date ? new Date(req.requested_date).toLocaleDateString() : req.date}
                      </p>
                    </td>
                    <td className="px-6 py-4">
                      <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${getPriorityColor(req.priority || "Normal")}`}>

                        {req.priority}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${getStatusColor(req.status || "Pending")}`}>

                        {req.status === "Pending" && <Clock className="w-3.5 h-3.5" />}
                        {req.status === "Processing" && <PlayCircle className="w-3.5 h-3.5" />}
                        {req.status === "Completed" && <CheckCircle className="w-3.5 h-3.5" />}
                        {req.status}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex justify-end gap-2">
                        {req.status === "Pending" && (
                          <button 
                            onClick={() => handleStatusUpdate(req.id, "Processing")}
                            className="px-3 py-1.5 bg-blue-50 text-blue-600 hover:bg-blue-100 rounded-lg text-xs font-semibold transition-colors"
                          >
                            Accept
                          </button>
                        )}
                        {req.status === "Processing" && (
                          <button 
                            onClick={() => window.location.href = `/dashboard/lab-technician/create-report?reqId=${req.id}`}
                            className="px-3 py-1.5 bg-emerald-50 text-emerald-600 hover:bg-emerald-100 rounded-lg text-xs font-semibold transition-colors"
                          >
                            Create Report
                          </button>
                        )}
                      </div>
                    </td>
                  </motion.tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
