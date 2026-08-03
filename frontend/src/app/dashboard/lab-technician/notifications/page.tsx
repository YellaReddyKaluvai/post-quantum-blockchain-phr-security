"use client";

import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Bell, CheckCircle2, Trash2, ShieldAlert, FileText, AlertCircle } from "lucide-react";
import { getLabTechNotifications, markLabNotificationRead, clearLabNotifications } from "@/lib/session";

interface LabTechNotifItem {
  id: string;
  type?: string;
  title?: string;
  message?: string;
  time?: string;
  read?: boolean;
  [key: string]: unknown;
}

export default function NotificationsPage() {
  const [notifications, setNotifications] = useState<LabTechNotifItem[]>([]);

  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchNotifs = async () => {
      try {
        const data = await getLabTechNotifications();
        setNotifications(data);
      } catch {
        setNotifications([
          { id: "1", type: "system", title: "PQC Keys Updated", message: "Your quantum-secure keys have been successfully rotated.", time: "10 mins ago", read: false },
          { id: "2", type: "doctor", title: "Urgent Test Request", message: "Dr. Sarah Smith requested an urgent CBC for PAT-8821.", time: "1 hour ago", read: false },
          { id: "3", type: "report", title: "Report Signed", message: "Report REP-9922 has been successfully signed and secured on the blockchain.", time: "2 hours ago", read: true },
        ]);
      } finally {
        setLoading(false);
      }
    };
    fetchNotifs();
  }, []);

  const handleMarkAsRead = async (id: string) => {
    try {
      await markLabNotificationRead(id);
      setNotifications(prev => prev.map(n => n.id === id ? { ...n, read: true } : n));
    } catch {
      setNotifications(prev => prev.map(n => n.id === id ? { ...n, read: true } : n));
    }
  };

  const handleClearAll = async () => {
    try {
      await clearLabNotifications();
      setNotifications([]);
    } catch {
      setNotifications([]);
    }
  };


  const unreadCount = notifications.filter(n => !n.read).length;

  const getIcon = (type: string) => {
    if (type === "system") return <ShieldAlert className="w-5 h-5 text-cyan-500" />;
    if (type === "doctor") return <AlertCircle className="w-5 h-5 text-amber-500" />;
    return <FileText className="w-5 h-5 text-emerald-500" />;
  };

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-800 flex items-center gap-2">
            Notifications
            {unreadCount > 0 && (
              <span className="bg-rose-500 text-white text-xs font-bold px-2 py-0.5 rounded-full">
                {unreadCount} New
              </span>
            )}
          </h1>
          <p className="text-sm text-slate-500">Updates regarding test requests, reports, and system alerts.</p>
        </div>
        <button
          onClick={handleClearAll}
          className="flex items-center gap-2 px-4 py-2 bg-white border border-slate-200 text-rose-600 rounded-xl text-sm font-semibold hover:bg-rose-50 hover:border-rose-200 transition-all shadow-sm"
        >
          <Trash2 className="w-4 h-4" />
          Clear All
        </button>
      </div>

      <div className="bg-white/80 backdrop-blur-md rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
        {loading ? (
          <div className="p-6 space-y-4">
            {[1, 2, 3].map(i => <div key={i} className="h-20 bg-slate-100 rounded-xl animate-pulse" />)}
          </div>
        ) : notifications.length === 0 ? (
          <div className="p-12 text-center text-slate-500">
            <Bell className="w-12 h-12 mx-auto text-slate-300 mb-4" />
            <p className="text-lg font-medium text-slate-700">No Notifications</p>
            <p className="text-sm mt-1">You&apos;re all caught up!</p>
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            <AnimatePresence>
              {notifications.map((notification: LabTechNotifItem) => (
                <motion.div

                  key={notification.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, height: 0 }}
                  className={`p-4 flex gap-4 transition-colors ${notification.read ? 'bg-white' : 'bg-cyan-50/30'}`}
                >
                  <div className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 ${notification.read ? 'bg-slate-100' : 'bg-white border border-cyan-100 shadow-sm'}`}>
                    {getIcon(notification.type || "system")}

                  </div>
                  <div className="flex-1">
                    <div className="flex justify-between items-start mb-1">
                      <h3 className={`text-sm font-bold ${notification.read ? 'text-slate-700' : 'text-slate-900'}`}>
                        {notification.title}
                      </h3>
                      <span className="text-xs font-medium text-slate-400 whitespace-nowrap ml-4">
                        {notification.time}
                      </span>
                    </div>
                    <p className={`text-sm ${notification.read ? 'text-slate-500' : 'text-slate-600 font-medium'}`}>
                      {notification.message}
                    </p>
                  </div>
                  {!notification.read && (
                    <button
                      onClick={() => handleMarkAsRead(notification.id)}
                      className="text-cyan-600 hover:text-cyan-700 p-2 rounded-full hover:bg-cyan-50 transition-colors self-center tooltip"
                      title="Mark as Read"
                    >
                      <CheckCircle2 className="w-5 h-5" />
                    </button>
                  )}
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        )}
      </div>
    </div>
  );
}
