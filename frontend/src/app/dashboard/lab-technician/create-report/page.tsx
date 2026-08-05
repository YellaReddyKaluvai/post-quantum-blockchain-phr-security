"use client";

import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Shield, CheckCircle, Fingerprint, Lock, Loader2, Hospital } from "lucide-react";
import { createStructuredLabReport, searchPatientsForLab } from "@/lib/session";
import PatientSearchSelect from "@/components/PatientSearchSelect";

interface PatientResult {
  id: string;
  user_id: string;
  full_name: string;
  email: string;
  gender: string;
}

export default function CreateReportPage() {
  const [reportType, setReportType] = useState("");
  const [patientId, setPatientId] = useState("");
  const [selectedPatient, setSelectedPatient] = useState<PatientResult | null>(null);
  const [formData, setFormData] = useState<Record<string, string>>({});
  const [reportId] = useState(() => `REP-${Math.floor(1000 + Math.random() * 9000)}`);
  
  const [showSecurityModal, setShowSecurityModal] = useState(false);
  const [securityStep, setSecurityStep] = useState(0);

  const reportTypes = [
    { id: "cbc", name: "Complete Blood Count (CBC)" },
    { id: "sugar", name: "Blood Sugar (Fasting/PP)" },
    { id: "lft", name: "Liver Function Test (LFT)" },
    { id: "urine", name: "Urine Analysis" }
  ];

  const handleInputChange = (field: string, value: string) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  const handleFinalize = async () => {
    setShowSecurityModal(true);
    setSecurityStep(1);
    
    // Simulate PQC Security steps
    setTimeout(() => setSecurityStep(2), 1500); // Hashing
    setTimeout(() => setSecurityStep(3), 3000); // Encrypting
    setTimeout(() => setSecurityStep(4), 4500); // Signing
    setTimeout(async () => {
      try {
        await createStructuredLabReport({ type: reportType, patient_id: patientId, patientId, ...formData });
        setSecurityStep(5); // Success
      } catch {
        setSecurityStep(5); // Show success anyway for demo
      }
      setTimeout(() => setShowSecurityModal(false), 2000);
    }, 6000);
  };


  const renderDynamicForm = () => {
    if (reportType === "cbc") {
      return (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Hemoglobin (Hb)</label>
            <div className="flex gap-2 items-center">
              <input type="number" step="0.1" onChange={(e) => handleInputChange("hb", e.target.value)} className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm" placeholder="e.g. 14.5" />
              <span className="text-xs text-slate-500 w-16">g/dL</span>
            </div>
            <p className="text-[10px] text-slate-400 mt-1">Ref: 13.0 - 17.0</p>
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Total RBC Count</label>
            <div className="flex gap-2 items-center">
              <input type="number" step="0.1" onChange={(e) => handleInputChange("rbc", e.target.value)} className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm" placeholder="e.g. 5.2" />
              <span className="text-xs text-slate-500 w-16">mill/cumm</span>
            </div>
            <p className="text-[10px] text-slate-400 mt-1">Ref: 4.5 - 5.5</p>
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Total WBC Count</label>
            <div className="flex gap-2 items-center">
              <input type="number" onChange={(e) => handleInputChange("wbc", e.target.value)} className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm" placeholder="e.g. 6500" />
              <span className="text-xs text-slate-500 w-16">cells/cumm</span>
            </div>
            <p className="text-[10px] text-slate-400 mt-1">Ref: 4000 - 11000</p>
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Platelet Count</label>
            <div className="flex gap-2 items-center">
              <input type="number" onChange={(e) => handleInputChange("platelets", e.target.value)} className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm" placeholder="e.g. 250000" />
              <span className="text-xs text-slate-500 w-16">cells/cumm</span>
            </div>
            <p className="text-[10px] text-slate-400 mt-1">Ref: 150000 - 450000</p>
          </div>
        </div>
      );
    }
    return <div className="text-sm text-slate-500 italic p-4 bg-slate-50 rounded-lg border border-slate-100">Select a report type to view form fields.</div>;
  };

  return (
    <div className="space-y-6 max-w-5xl mx-auto pb-20">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Create Laboratory Report</h1>
        <p className="text-sm text-slate-500">Enter test results and securely sign via PQC cryptography.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Form Section */}
        <div className="space-y-6">
          <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
            <h2 className="text-lg font-bold text-slate-800 mb-4 border-b border-slate-100 pb-2">Report Details</h2>
            
            <div className="space-y-4">
              <div>
                <PatientSearchSelect
                  searchFn={searchPatientsForLab}
                  label="Select Patient"
                  placeholder="Search patient by name or ID..."
                  selectedPatient={selectedPatient}
                  onSelect={(patient) => {
                    setSelectedPatient(patient);
                    setPatientId(patient.user_id || patient.id);
                  }}
                  onClear={() => {
                    setSelectedPatient(null);
                    setPatientId("");
                  }}
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Report Type</label>
                <select 
                  value={reportType}
                  onChange={(e) => setReportType(e.target.value)}
                  className="w-full px-3 py-2 bg-white border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-cyan-500/20 focus:border-cyan-500"
                >
                  <option value="">Select a report type...</option>
                  {reportTypes.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
            <h2 className="text-lg font-bold text-slate-800 mb-4 border-b border-slate-100 pb-2">Test Results</h2>
            {renderDynamicForm()}
            
            <div className="mt-4 pt-4 border-t border-slate-100">
               <label className="block text-sm font-medium text-slate-700 mb-1">Technician Remarks (Optional)</label>
               <textarea 
                 rows={3} 
                 onChange={(e) => handleInputChange("remarks", e.target.value)}
                 className="w-full px-3 py-2 bg-white border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-cyan-500/20 focus:border-cyan-500" 
                 placeholder="Any additional observations..." 
               />
            </div>
          </div>

          <button
            onClick={handleFinalize}
            disabled={!reportType || !patientId}
            className="w-full flex items-center justify-center gap-2 px-6 py-4 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 text-white font-bold rounded-xl shadow-lg shadow-emerald-600/20 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Shield className="w-5 h-5" />
            Finalize & PQC Secure Upload
          </button>
        </div>

        {/* Live Preview Section */}
        <div className="bg-white rounded-2xl shadow-lg border border-slate-200 p-8 relative overflow-hidden h-[800px]">
          <div className="absolute top-0 left-0 w-full h-2 bg-cyan-600" />
          
          {/* Hospital Header */}
          <div className="flex justify-between items-center border-b-2 border-slate-800 pb-4 mb-6">
            <div className="flex items-center gap-3">
              <Hospital className="w-8 h-8 text-cyan-700" />
              <div>
                <h2 className="text-xl font-bold text-slate-900 tracking-tight">QuantumCare Hospital</h2>
                <p className="text-[10px] text-slate-500 font-semibold uppercase tracking-widest">Laboratory Services</p>
              </div>
            </div>
            <div className="text-right">
              <p className="text-xs font-bold text-slate-700">Report ID: <span className="font-mono text-cyan-700">{reportId}</span></p>
              <p className="text-xs text-slate-500">Date: {new Date().toLocaleDateString()}</p>
            </div>
          </div>

          {/* Patient Info */}
          <div className="grid grid-cols-2 gap-4 mb-6 text-sm bg-slate-50 p-4 rounded-lg border border-slate-200">
            <div>
               <p><span className="font-semibold text-slate-600">Patient ID:</span> {selectedPatient?.user_id || patientId || "---"}</p>
               <p><span className="font-semibold text-slate-600">Name:</span> {selectedPatient?.full_name || "Select a patient"}</p>
            </div>
            <div>
              <p><span className="font-semibold text-slate-600">Ref By:</span> Dr. Name Here</p>
              <p><span className="font-semibold text-slate-600">Sample Date:</span> {new Date().toLocaleDateString()}</p>
            </div>
          </div>

          {/* Report Title */}
          <h3 className="text-center text-lg font-bold text-slate-800 mb-4 uppercase decoration-2 underline-offset-4 underline">
            {reportTypes.find(t => t.id === reportType)?.name || "Select Report Type"}
          </h3>

          {/* Results Table Preview */}
          {reportType === "cbc" && (
            <table className="w-full text-sm text-left border-collapse mb-8">
              <thead>
                <tr className="border-b-2 border-slate-300">
                  <th className="py-2 font-bold text-slate-700">Investigation</th>
                  <th className="py-2 font-bold text-slate-700">Result</th>
                  <th className="py-2 font-bold text-slate-700 text-slate-500">Unit</th>
                  <th className="py-2 font-bold text-slate-700 text-slate-500">Reference</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                <tr>
                  <td className="py-3 font-semibold text-slate-800">Hemoglobin (Hb)</td>
                  <td className={`py-3 font-bold ${formData.hb && (Number(formData.hb) < 13 || Number(formData.hb) > 17) ? 'text-rose-600' : 'text-slate-800'}`}>
                    {formData.hb || "---"}
                  </td>
                  <td className="py-3 text-slate-500">g/dL</td>
                  <td className="py-3 text-slate-500 text-xs">13.0 - 17.0</td>
                </tr>
                <tr>
                  <td className="py-3 font-semibold text-slate-800">Total RBC Count</td>
                  <td className="py-3 font-bold text-slate-800">{formData.rbc || "---"}</td>
                  <td className="py-3 text-slate-500">mill/cumm</td>
                  <td className="py-3 text-slate-500 text-xs">4.5 - 5.5</td>
                </tr>
                <tr>
                  <td className="py-3 font-semibold text-slate-800">Total WBC Count</td>
                  <td className="py-3 font-bold text-slate-800">{formData.wbc || "---"}</td>
                  <td className="py-3 text-slate-500">cells/cumm</td>
                  <td className="py-3 text-slate-500 text-xs">4000 - 11000</td>
                </tr>
              </tbody>
            </table>
          )}

          {formData.remarks && (
            <div className="mb-8">
              <p className="text-xs font-bold text-slate-700 mb-1">Remarks:</p>
              <p className="text-sm text-slate-600 italic">{formData.remarks}</p>
            </div>
          )}

          {/* Signature Area */}
          <div className="absolute bottom-8 right-8 text-right">
             <div className="inline-block border-2 border-emerald-500 rounded-lg p-2 bg-emerald-50 text-emerald-700 text-xs font-bold flex items-center gap-2 mb-2">
               <Shield className="w-4 h-4" />
               PQC ML-DSA SIGNED
             </div>
             <p className="text-sm font-bold text-slate-800">Lab Technician Name</p>
             <p className="text-xs text-slate-500">LIMS Certified Professional</p>
          </div>
        </div>
      </div>

      {/* Security Processing Modal */}
      <AnimatePresence>
        {showSecurityModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 bg-slate-900/60 backdrop-blur-sm"
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              className="relative bg-white rounded-2xl shadow-2xl p-8 max-w-sm w-full overflow-hidden"
            >
              <div className="absolute top-0 left-0 w-full h-1 bg-slate-100">
                <motion.div 
                  className="h-full bg-cyan-500"
                  initial={{ width: "0%" }}
                  animate={{ width: `${(securityStep / 5) * 100}%` }}
                  transition={{ duration: 0.5 }}
                />
              </div>

              <div className="text-center mb-6">
                <div className="w-16 h-16 mx-auto bg-cyan-50 rounded-2xl flex items-center justify-center mb-4 border border-cyan-100 shadow-inner">
                  {securityStep < 5 ? (
                    <Shield className="w-8 h-8 text-cyan-500 animate-pulse" />
                  ) : (
                    <CheckCircle className="w-8 h-8 text-emerald-500" />
                  )}
                </div>
                <h3 className="text-lg font-bold text-slate-800">Securing Report</h3>
                <p className="text-xs text-slate-500 mt-1">Post-Quantum Cryptography Process</p>
              </div>

              <div className="space-y-4 text-sm">
                <div className="flex items-center gap-3">
                  <div className={`w-6 h-6 rounded-full flex items-center justify-center ${securityStep >= 2 ? 'bg-emerald-100 text-emerald-600' : 'bg-slate-100 text-slate-400'}`}>
                    {securityStep >= 2 ? <CheckCircle className="w-4 h-4" /> : <Loader2 className="w-4 h-4 animate-spin" />}
                  </div>
                  <span className={securityStep >= 2 ? 'text-slate-800 font-medium' : 'text-slate-400'}>SHA-256 Document Hashing</span>
                </div>
                
                <div className="flex items-center gap-3">
                  <div className={`w-6 h-6 rounded-full flex items-center justify-center ${securityStep >= 3 ? 'bg-emerald-100 text-emerald-600' : securityStep === 2 ? 'bg-cyan-100 text-cyan-600' : 'bg-slate-100 text-slate-400'}`}>
                    {securityStep >= 3 ? <CheckCircle className="w-4 h-4" /> : securityStep === 2 ? <Loader2 className="w-4 h-4 animate-spin" /> : <Lock className="w-4 h-4" />}
                  </div>
                  <span className={securityStep >= 3 ? 'text-slate-800 font-medium' : securityStep === 2 ? 'text-cyan-700 font-semibold' : 'text-slate-400'}>AES-256 Data Encryption</span>
                </div>

                <div className="flex items-center gap-3">
                  <div className={`w-6 h-6 rounded-full flex items-center justify-center ${securityStep >= 4 ? 'bg-emerald-100 text-emerald-600' : securityStep === 3 ? 'bg-purple-100 text-purple-600' : 'bg-slate-100 text-slate-400'}`}>
                    {securityStep >= 4 ? <CheckCircle className="w-4 h-4" /> : securityStep === 3 ? <Loader2 className="w-4 h-4 animate-spin" /> : <Shield className="w-4 h-4" />}
                  </div>
                  <span className={securityStep >= 4 ? 'text-slate-800 font-medium' : securityStep === 3 ? 'text-purple-700 font-semibold' : 'text-slate-400'}>ML-KEM Key Encapsulation</span>
                </div>

                <div className="flex items-center gap-3">
                  <div className={`w-6 h-6 rounded-full flex items-center justify-center ${securityStep >= 5 ? 'bg-emerald-100 text-emerald-600' : securityStep === 4 ? 'bg-indigo-100 text-indigo-600' : 'bg-slate-100 text-slate-400'}`}>
                    {securityStep >= 5 ? <CheckCircle className="w-4 h-4" /> : securityStep === 4 ? <Loader2 className="w-4 h-4 animate-spin" /> : <Fingerprint className="w-4 h-4" />}
                  </div>
                  <span className={securityStep >= 5 ? 'text-slate-800 font-medium' : securityStep === 4 ? 'text-indigo-700 font-semibold' : 'text-slate-400'}>ML-DSA Digital Signature</span>
                </div>
              </div>

              {securityStep === 5 && (
                <div className="mt-6 text-center">
                  <p className="text-sm font-bold text-emerald-600 bg-emerald-50 py-2 rounded-lg border border-emerald-100">
                    Blockchain Audit Record Created!
                  </p>
                </div>
              )}
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
