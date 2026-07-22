"use client";

import React from "react";
import { User, Stethoscope, TestTube, Activity } from "lucide-react";
import type { AppRole } from "@/lib/iam";

interface RoleSelectorProps {
  selectedRole: AppRole | null;
  onSelect: (role: AppRole) => void;
}

const roles: { role: AppRole; icon: React.ElementType; description: string; color: string }[] = [
  { role: "Patient", icon: User, description: "Access personal health records", color: "text-blue-500" },
  { role: "Doctor", icon: Stethoscope, description: "Manage patients and diagnoses", color: "text-teal-500" },
  { role: "Nurse", icon: Activity, description: "Update vitals and care plans", color: "text-rose-500" },
  { role: "Lab Technician", icon: TestTube, description: "Upload and manage lab reports", color: "text-purple-500" },
];

export default function RoleSelector({ selectedRole, onSelect }: RoleSelectorProps) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
      {roles.map(({ role, icon: Icon, description, color }) => (
        <button
          key={role}
          type="button"
          onClick={() => onSelect(role)}
          className={`relative p-4 rounded-xl border-2 text-left transition-all duration-300 flex items-start space-x-3
            ${selectedRole === role 
              ? "border-teal-500 bg-teal-50 shadow-md transform scale-[1.02]" 
              : "border-slate-200 bg-white hover:border-teal-300 hover:bg-slate-50 hover:shadow-sm"
            }
          `}
        >
          <div className={`p-2 rounded-lg bg-white shadow-sm border border-slate-100 ${color}`}>
            <Icon className="w-6 h-6" />
          </div>
          <div>
            <h4 className="font-semibold text-slate-800">{role}</h4>
            <p className="text-xs text-slate-500 mt-1">{description}</p>
          </div>
          
          {selectedRole === role && (
            <div className="absolute top-2 right-2">
              <div className="w-3 h-3 rounded-full bg-teal-500 shadow-[0_0_8px_rgba(20,184,166,0.6)]" />
            </div>
          )}
        </button>
      ))}
    </div>
  );
}
