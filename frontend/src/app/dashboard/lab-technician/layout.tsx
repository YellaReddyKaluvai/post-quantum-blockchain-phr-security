"use client";

import React, { useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  LayoutDashboard,
  ClipboardList,
  Search,
  FilePlus,
  FileCheck,
  Film,
  Bell,
  User,
  LogOut,
  FlaskConical,
  Menu,
  X,
  ChevronLeft,
} from "lucide-react";
import { logout } from "@/lib/session";
import { useAuth } from "@/context/AuthContext";

const navItems = [
  { label: "Dashboard", icon: LayoutDashboard, href: "/dashboard/lab-technician" },
  { label: "Pending Test Requests", icon: ClipboardList, href: "/dashboard/lab-technician/requests" },
  { label: "Patient Search", icon: Search, href: "/dashboard/lab-technician/patients" },
  { label: "Create Report", icon: FilePlus, href: "/dashboard/lab-technician/create-report" },
  { label: "Laboratory Reports", icon: FileCheck, href: "/dashboard/lab-technician/reports" },
  { label: "Imaging Reports", icon: Film, href: "/dashboard/lab-technician/imaging" },
  { label: "Notifications", icon: Bell, href: "/dashboard/lab-technician/notifications" },
  { label: "My Profile", icon: User, href: "/dashboard/lab-technician/profile" },
];

export default function LabTechnicianLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { clearSession } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);

  const handleLogout = async () => {
    await logout();
    clearSession();
    router.push("/login");
  };

  const isActive = (href: string) => {
    if (href === "/dashboard/lab-technician") return pathname === "/dashboard/lab-technician";
    return pathname.startsWith(href);
  };

  const sidebarContent = (
    <div className="flex flex-col h-full">
      {/* Logo */}
      <div className="px-5 py-6 border-b border-slate-700/50">
        <Link href="/dashboard/lab-technician" className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-cyan-400 to-teal-500 flex items-center justify-center shadow-lg shadow-cyan-900/30 flex-shrink-0">
            <FlaskConical className="w-5 h-5 text-white" />
          </div>
          {!collapsed && (
            <motion.div
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              className="flex flex-col"
            >
              <span className="text-lg font-extrabold tracking-wider text-white">QuantumCare</span>
              <span className="text-[10px] font-bold tracking-widest text-cyan-400/70 uppercase">LIMS Portal</span>
            </motion.div>
          )}
        </Link>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {navItems.map((item) => {
          const active = isActive(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={() => setSidebarOpen(false)}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-semibold transition-all duration-200 group ${
                active
                  ? "bg-cyan-500/20 text-cyan-400 shadow-sm shadow-cyan-500/10"
                  : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"
              }`}
            >
              <item.icon
                className={`w-5 h-5 flex-shrink-0 transition-colors ${
                  active ? "text-cyan-400" : "text-slate-500 group-hover:text-slate-300"
                }`}
              />
              {!collapsed && <span>{item.label}</span>}
              {active && !collapsed && (
                <motion.div
                  layoutId="active-indicator"
                  className="ml-auto w-1.5 h-1.5 rounded-full bg-cyan-400"
                />
              )}
            </Link>
          );
        })}
      </nav>

      {/* Collapse toggle (desktop only) */}
      <div className="hidden lg:block px-3 py-2 border-t border-slate-700/50">
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-semibold text-slate-500 hover:bg-slate-800 hover:text-slate-300 transition-all w-full"
        >
          <ChevronLeft
            className={`w-5 h-5 transition-transform duration-300 ${collapsed ? "rotate-180" : ""}`}
          />
          {!collapsed && <span>Collapse</span>}
        </button>
      </div>

      {/* Logout */}
      <div className="px-3 py-4 border-t border-slate-700/50">
        <button
          onClick={handleLogout}
          className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-semibold text-rose-400 hover:bg-rose-500/10 hover:text-rose-300 transition-all w-full"
        >
          <LogOut className="w-5 h-5 flex-shrink-0" />
          {!collapsed && <span>Logout</span>}
        </button>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-slate-50 flex">
      {/* Desktop Sidebar */}
      <motion.aside
        animate={{ width: collapsed ? 72 : 260 }}
        transition={{ duration: 0.3, ease: "easeInOut" }}
        className="hidden lg:flex flex-col bg-slate-900 border-r border-slate-700/50 fixed top-0 left-0 h-screen z-30"
      >
        {sidebarContent}
      </motion.aside>

      {/* Mobile Sidebar Overlay */}
      <AnimatePresence>
        {sidebarOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40 lg:hidden"
              onClick={() => setSidebarOpen(false)}
            />
            <motion.aside
              initial={{ x: -280 }}
              animate={{ x: 0 }}
              exit={{ x: -280 }}
              transition={{ type: "spring", damping: 25, stiffness: 300 }}
              className="fixed top-0 left-0 w-[260px] h-screen bg-slate-900 z-50 lg:hidden shadow-2xl"
            >
              <button
                onClick={() => setSidebarOpen(false)}
                className="absolute top-5 right-4 text-slate-400 hover:text-white transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
              {sidebarContent}
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      {/* Main Content */}
      <motion.div
        animate={{ marginLeft: collapsed ? 72 : 260 }}
        transition={{ duration: 0.3, ease: "easeInOut" }}
        className="flex-1 min-h-screen flex flex-col lg:ml-0"
        style={{ marginLeft: 0 }}
      >
        {/* Top Header */}
        <header className="sticky top-0 z-20 bg-white/80 backdrop-blur-xl border-b border-slate-200/60 px-4 sm:px-8 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <button
                onClick={() => setSidebarOpen(true)}
                className="lg:hidden p-2 rounded-xl hover:bg-slate-100 text-slate-600 transition-colors"
              >
                <Menu className="w-5 h-5" />
              </button>
              <div>
                <h1 className="text-lg sm:text-xl font-extrabold text-slate-800">Laboratory Technician Dashboard</h1>
                <p className="text-xs text-slate-500 font-medium hidden sm:block">LIMS Portal</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-full bg-cyan-50 border border-cyan-100">
                <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                <span className="text-xs font-bold text-cyan-700">Quantum-Secure</span>
              </div>
              <button
                onClick={handleLogout}
                className="lg:hidden p-2 rounded-xl hover:bg-rose-50 text-rose-500 transition-colors"
              >
                <LogOut className="w-5 h-5" />
              </button>
            </div>
          </div>
        </header>

        {/* Page Content */}
        <main className="flex-1 p-4 sm:p-6 lg:p-8">
          {children}
        </main>
      </motion.div>
    </div>
  );
}
