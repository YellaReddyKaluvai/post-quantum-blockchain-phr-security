"use client";

import React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { roleModules, type AppRole, dashboardRouteMap } from "@/lib/iam";
import ProtectedRoute from "@/components/ProtectedRoute";
import { LogOut, ShieldCheck } from "lucide-react";
import { logout } from "@/lib/session";
import { useAuth } from "@/context/AuthContext";

type Props = {
  role: AppRole;
  title: string;
  description: string;
  children?: React.ReactNode;
};

export default function RoleDashboard({ role, title, description, children }: Props) {
  const modules = roleModules[role] || [];
  const router = useRouter();
  const { clearSession } = useAuth();

  const handleLogout = async () => {
    await logout();
    clearSession();
    router.push("/login");
  };

  return (
    <ProtectedRoute route={dashboardRouteMap[role]}>
      <main className="min-h-screen p-6 sm:p-10 text-slate-800">
        <section className="mx-auto max-w-7xl">
          <div className="overflow-hidden rounded-[2rem] border border-white/70 bg-white/80 shadow-[0_20px_70px_-20px_rgba(8,145,178,0.25)] backdrop-blur-xl">
            <div className="grid lg:grid-cols-[280px_1fr]">
              <aside className="border-b border-slate-100 bg-slate-50/70 p-6 lg:border-b-0 lg:border-r">
                <div className="flex items-center gap-3">
                  <div className="rounded-2xl bg-cyan-600 p-3 text-white">
                    <ShieldCheck className="h-5 w-5" />
                  </div>
                  <div>
                    <p className="text-xs font-black uppercase tracking-[0.35em] text-teal-600">{role}</p>
                    <h2 className="text-xl font-black text-cyan-950">QuantumCare</h2>
                  </div>
                </div>

                <nav className="mt-8 space-y-2">
                  {modules.map((module) => (
                    <div key={module} className="rounded-2xl bg-white px-4 py-3 text-sm font-bold text-slate-700 shadow-sm">
                      {module}
                    </div>
                  ))}
                </nav>

                <button onClick={handleLogout} className="mt-8 inline-flex w-full items-center justify-center gap-2 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-bold text-rose-700 hover:bg-rose-100 transition-colors">
                  <LogOut className="h-4 w-4" />
                  Logout
                </button>
              </aside>

              <div className="p-8 sm:p-10">
                <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
                  <div>
                    <p className="text-xs font-black uppercase tracking-[0.35em] text-teal-600">{role}</p>
                    <h1 className="mt-2 text-3xl font-black text-cyan-950 sm:text-4xl">{title}</h1>
                    <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">{description}</p>
                  </div>
                  <Link href={dashboardRouteMap[role]} className="inline-flex items-center justify-center rounded-full border border-cyan-200 bg-cyan-50 px-4 py-2 text-sm font-bold text-cyan-800">
                    Active Role
                  </Link>
                </div>

                {!children && (
                  <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                    {modules.map((module) => (
                      <article key={module} className="rounded-3xl border border-slate-100 bg-white p-5 shadow-sm">
                        <p className="text-sm font-black text-teal-700">{module}</p>
                        <p className="mt-2 text-sm text-slate-500">Authorized under role-based policy and audit logging.</p>
                      </article>
                    ))}
                  </div>
                )}
                
                {children}
              </div>
            </div>
          </div>
        </section>
      </main>
    </ProtectedRoute>
  );
}
