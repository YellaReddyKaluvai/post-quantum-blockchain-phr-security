"use client";

import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Bell, Check, Trash2 } from "lucide-react";
import { getDoctorNotifications, markDoctorNotificationRead, clearDoctorNotifications } from "@/lib/session";

interface DoctorNotif {
  id: string;
  is_read?: boolean;
  message?: string;
  date?: string;
  [key: string]: unknown;
}

export default function DoctorNotifications() {
  const [notifications, setNotifications] = useState<DoctorNotif[]>([]);

  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchNotifs() {
      try {
        const data = await getDoctorNotifications();
        setNotifications(data);
      } catch (error) {
        console.error("Error fetching notifications:", error);
      } finally {
        setLoading(false);
      }
    }
    fetchNotifs();
  }, []);

  const handleMarkRead = async (id: string) => {
    try {
      await markDoctorNotificationRead(id);
      setNotifications(notifications.map(n => n.id === id ? { ...n, is_read: true } : n));
    } catch (error) {
      console.error(error);
    }
  };

  const handleClearAll = async () => {
    try {
      await clearDoctorNotifications();
      setNotifications([]);
    } catch (error) {
      console.error(error);
    }
  };

  if (loading) {
    return <div className="space-y-4">{[1,2,3].map(i => <div key={i} className="h-20 bg-slate-200 animate-pulse rounded-2xl" />)}</div>;
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-6">
        <div className="flex items-center gap-3">
          <Bell className="w-6 h-6 text-amber-500" />
          <h1 className="text-2xl font-bold text-slate-800">Notifications</h1>
        </div>
        {notifications.length > 0 && (
          <button onClick={handleClearAll} className="flex items-center gap-2 px-4 py-2 bg-rose-50 hover:bg-rose-100 text-rose-600 rounded-xl text-sm font-bold transition-colors">
            <Trash2 className="w-4 h-4" /> Clear All
          </button>
        )}
      </div>

      <div className="space-y-4">
        {notifications.length === 0 ? (
          <div className="text-center py-12 bg-white rounded-2xl shadow-sm border border-slate-100 text-slate-500">
            No notifications. You&apos;re all caught up!
          </div>
        ) : (
          notifications.map((notif: DoctorNotif, i: number) => (
            <motion.div
              key={notif.id || i}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
              className={`p-4 rounded-2xl border transition-all flex items-start justify-between gap-4 ${notif.is_read ? "bg-slate-50 border-slate-100" : "bg-white border-cyan-200 shadow-sm"}`}
            >
              <div>
                <p className={`text-sm ${notif.is_read ? "text-slate-600" : "font-semibold text-slate-800"}`}>{notif.message}</p>
                <p className="text-xs text-slate-400 mt-1">{new Date(notif.date || Date.now()).toLocaleString()}</p>
              </div>

              {!notif.is_read && (
                <button onClick={() => handleMarkRead(notif.id)} className="p-2 text-cyan-600 hover:bg-cyan-50 rounded-xl transition-colors" title="Mark as read">
                  <Check className="w-5 h-5" />
                </button>
              )}
            </motion.div>
          ))
        )}
      </div>
    </div>
  );
}
