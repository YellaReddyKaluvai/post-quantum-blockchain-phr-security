"use client";

import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ShieldCheck, ArrowRight, ArrowLeft, Loader2, CheckCircle2 } from "lucide-react";
import Link from "next/link";
import { register } from "../../lib/session";
import RoleSelector from "../../components/RoleSelector";
import PasswordStrength from "../../components/PasswordStrength";
import type { AppRole } from "../../lib/iam";

export default function SignupPage() {
  const [step, setStep] = useState(1);
  const [formData, setFormData] = useState({
    role: "" as AppRole | "",
    full_name: "",
    email: "",
    gender: "Male",
    date_of_birth: "",
    blood_group: "",
    specialization: "",
    password: "",
    confirm_password: ""
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  const handleNext = () => {
    setError("");
    if (step === 1 && !formData.role) {
      setError("Please select a role.");
      return;
    }
    if (step === 2) {
      if (!formData.full_name || !formData.email || !formData.date_of_birth) {
        setError("Please fill all required fields.");
        return;
      }
    }
    setStep(s => s + 1);
  };

  const handlePrev = () => setStep(s => s - 1);

  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (formData.password !== formData.confirm_password) {
      setError("Passwords do not match.");
      return;
    }
    
    // Basic password validation
    if (formData.password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }

    try {
      setLoading(true);
      await register({
        full_name: formData.full_name,
        email: formData.email,
        password: formData.password,
        confirm_password: formData.confirm_password,
        role: formData.role,
        gender: formData.gender,
        date_of_birth: formData.date_of_birth,
        blood_group: formData.role === "Patient" ? formData.blood_group : null,
        specialization: formData.role !== "Patient" ? formData.specialization : null
      });
      setSuccess(true);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Registration failed.");
    } finally {
      setLoading(false);
    }
  };

  const inputClass = "w-full bg-cyan-50/50 border border-cyan-100 shadow-[inset_0_2px_4px_rgba(8,145,178,0.05)] rounded-2xl py-3.5 pl-4 pr-4 text-slate-800 focus:bg-white focus:outline-none focus:border-cyan-400 focus:ring-[3px] focus:ring-cyan-100 transition-all text-sm font-bold placeholder-slate-500";
  const labelClass = "block text-[11px] font-extrabold text-teal-600/80 mb-2 uppercase tracking-widest";

  return (
    <div className="min-h-screen text-slate-700 flex flex-col pt-10 pb-10 items-center p-4 relative overflow-hidden"
      style={{ background: "linear-gradient(135deg, #f9feff 0%, #f0fafd 20%, #f5fdf9 60%, #fdfffe 100%)" }}>
      {/* Decorative blobs */}
      <div className="absolute top-[-10%] right-[-10%] w-[50%] h-[50%] rounded-full bg-cyan-300/40 blur-[120px] pointer-events-none float-anim" />
      <div className="absolute bottom-[-10%] left-[-10%] w-[50%] h-[50%] rounded-full bg-emerald-300/30 blur-[120px] pointer-events-none float-anim" style={{ animationDelay: "1.5s" }} />

      <div className="absolute inset-0 z-[-1] bg-[linear-gradient(to_right,#0891b20a_1px,transparent_1px),linear-gradient(to_bottom,#0891b20a_1px,transparent_1px)] bg-[size:32px_32px] [mask-image:radial-gradient(ellipse_70%_60%_at_50%_0%,#000_70%,transparent_100%)]" />

      <div className="w-full max-w-xl relative z-10">
        <Link href="/" className="flex items-center justify-center gap-3 mb-8 hover:opacity-80 transition-opacity">
          <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-cyan-400 to-teal-500 flex items-center justify-center shadow-lg shadow-cyan-200">
            <ShieldCheck className="w-6 h-6 text-white" />
          </div>
          <span className="text-2xl font-extrabold tracking-wider bg-clip-text text-transparent bg-gradient-to-r from-slate-800 to-slate-600 drop-shadow-sm">
            AEGIS
          </span>
        </Link>

        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="card-3d gradient-border-card p-8 sm:p-10 rounded-[2rem] border border-white/60 shadow-[0_15px_60px_-15px_rgba(8,145,178,0.25)] relative overflow-hidden bg-white/80 backdrop-blur-sm"
        >
          {success ? (
            <motion.div initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} className="text-center py-10">
              <div className="w-20 h-20 bg-emerald-100 text-emerald-500 rounded-full flex items-center justify-center mx-auto mb-6 shadow-inner">
                <CheckCircle2 className="w-10 h-10" />
              </div>
              <h2 className="text-3xl font-black mb-4 text-emerald-800">Registration Pending</h2>
              <p className="text-slate-600 mb-8 max-w-sm mx-auto">Your registration request has been successfully submitted. An administrator will review and verify your identity before granting access to the system.</p>
              <Link href="/login" className="inline-flex items-center justify-center gap-2 bg-gradient-to-r from-emerald-500 to-teal-600 text-white px-8 py-3.5 rounded-2xl font-extrabold shadow-lg shadow-emerald-200 hover:shadow-xl hover:-translate-y-1 transition-all">
                Proceed to Login <ArrowRight className="w-5 h-5" />
              </Link>
            </motion.div>
          ) : (
            <>
              <div className="mb-8">
                <div className="flex justify-between items-center mb-6">
                  <h2 className="text-2xl font-black text-cyan-900">Registration</h2>
                  <div className="flex gap-2">
                    <div className={`h-2 w-8 rounded-full ${step >= 1 ? "bg-teal-500" : "bg-slate-200"} transition-colors`} />
                    <div className={`h-2 w-8 rounded-full ${step >= 2 ? "bg-teal-500" : "bg-slate-200"} transition-colors`} />
                    <div className={`h-2 w-8 rounded-full ${step >= 3 ? "bg-teal-500" : "bg-slate-200"} transition-colors`} />
                  </div>
                </div>
                {error && <div className="p-3 mb-4 rounded-xl bg-rose-50 border border-rose-100 text-rose-600 text-xs font-semibold animate-pulse">{error}</div>}
              </div>

              <AnimatePresence mode="wait">
                {step === 1 && (
                  <motion.div key="step1" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
                    <h3 className="text-sm font-bold text-slate-500 mb-4 uppercase tracking-wider">Select your Role</h3>
                    <RoleSelector selectedRole={formData.role as AppRole} onSelect={(r) => setFormData({...formData, role: r})} />
                    
                    <button onClick={handleNext} disabled={!formData.role} className="w-full mt-8 bg-gradient-to-r from-cyan-500 to-teal-500 hover:from-cyan-400 hover:to-teal-400 text-white py-4 rounded-2xl font-extrabold transition-all flex items-center justify-center gap-2 disabled:opacity-50">
                      Next Step <ArrowRight className="w-5 h-5" />
                    </button>
                  </motion.div>
                )}

                {step === 2 && (
                  <motion.div key="step2" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} className="space-y-4">
                    <div>
                      <label className={labelClass}>Full Name</label>
                      <input type="text" required value={formData.full_name} onChange={e => setFormData({...formData, full_name: e.target.value})} className={inputClass} placeholder="Alice Smith" />
                    </div>
                    <div>
                      <label className={labelClass}>Email Address</label>
                      <input type="email" required value={formData.email} onChange={e => setFormData({...formData, email: e.target.value})} className={inputClass} placeholder="alice@example.com" />
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className={labelClass}>Gender</label>
                        <select value={formData.gender} onChange={e => setFormData({...formData, gender: e.target.value})} className={inputClass}>
                          <option>Male</option>
                          <option>Female</option>
                          <option>Other</option>
                        </select>
                      </div>
                      <div>
                        <label className={labelClass}>Date of Birth</label>
                        <input type="date" required value={formData.date_of_birth} onChange={e => setFormData({...formData, date_of_birth: e.target.value})} className={inputClass} />
                      </div>
                    </div>
                    
                    {formData.role === "Patient" && (
                      <div>
                        <label className={labelClass}>Blood Group (Optional)</label>
                        <input type="text" value={formData.blood_group} onChange={e => setFormData({...formData, blood_group: e.target.value})} className={inputClass} placeholder="O+" />
                      </div>
                    )}
                    {(formData.role === "Doctor" || formData.role === "Nurse" || formData.role === "Lab Technician") && (
                      <div>
                        <label className={labelClass}>Specialization</label>
                        <input type="text" required value={formData.specialization} onChange={e => setFormData({...formData, specialization: e.target.value})} className={inputClass} placeholder="Cardiology" />
                      </div>
                    )}

                    <div className="flex gap-4 mt-8">
                      <button onClick={handlePrev} className="flex-1 bg-slate-100 hover:bg-slate-200 text-slate-700 py-4 rounded-2xl font-extrabold transition-all flex items-center justify-center gap-2">
                        <ArrowLeft className="w-5 h-5" /> Back
                      </button>
                      <button onClick={handleNext} className="flex-[2] bg-gradient-to-r from-cyan-500 to-teal-500 hover:from-cyan-400 hover:to-teal-400 text-white py-4 rounded-2xl font-extrabold transition-all flex items-center justify-center gap-2">
                        Next Step <ArrowRight className="w-5 h-5" />
                      </button>
                    </div>
                  </motion.div>
                )}

                {step === 3 && (
                  <motion.form key="step3" onSubmit={handleSignup} initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} className="space-y-4">
                    <div>
                      <label className={labelClass}>Master Password</label>
                      <input type="password" required value={formData.password} onChange={e => setFormData({...formData, password: e.target.value})} className={inputClass} placeholder="••••••••" />
                      <PasswordStrength password={formData.password} />
                    </div>
                    <div>
                      <label className={labelClass}>Confirm Password</label>
                      <input type="password" required value={formData.confirm_password} onChange={e => setFormData({...formData, confirm_password: e.target.value})} className={inputClass} placeholder="••••••••" />
                    </div>

                    <div className="flex gap-4 mt-8">
                      <button type="button" onClick={handlePrev} className="flex-1 bg-slate-100 hover:bg-slate-200 text-slate-700 py-4 rounded-2xl font-extrabold transition-all flex items-center justify-center gap-2">
                        <ArrowLeft className="w-5 h-5" /> Back
                      </button>
                      <button type="submit" disabled={loading} className="flex-[2] bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-white py-4 rounded-2xl font-extrabold transition-all flex items-center justify-center gap-2 shadow-lg shadow-emerald-200">
                        {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : "Complete Registration"}
                      </button>
                    </div>
                  </motion.form>
                )}
              </AnimatePresence>
            </>
          )}

          {!success && (
            <div className="mt-8 text-center text-sm font-medium text-slate-500">
              Already have an account? <Link href="/login" className="text-cyan-600 hover:text-cyan-500 font-extrabold ml-1 underline decoration-cyan-300 underline-offset-4">Sign in here</Link>
            </div>
          )}
        </motion.div>
      </div>
    </div>
  );
}
