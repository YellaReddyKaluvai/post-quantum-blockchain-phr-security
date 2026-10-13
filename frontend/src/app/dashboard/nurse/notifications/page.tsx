"use client";

import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Bell, Check, Trash2 } from "lucide-react";
import { getNurseNotifications, markNurseNotificationRead, clearNurseNotifications } from "@/lib/session";

// Mirrors the backend NotificationItem exactly.
interface NurseNotifItem {
  id: string;
  notification_type?: string;
  title?: string;
  body?: string;
  read_at?: string | null;
  created_at?: string;
}

export default function NurseNotificationsPage() {
  const [notifications, setNotifications] = useState<NurseNotifItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    getNurseNotifications()
      .then(setNotifications)
      .catch((error) => {
        console.error(error);
        setNotifications([]);
        setLoadError("Could not load notifications. Check that the backend is running.");
      })
      .finally(() => setLoading(false));
  }, []);

  const handleMarkRead = async (id: string) => {
    try {
      await markNurseNotificationRead(id);
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, read_at: new Date().toISOString() } : n))
      );
    } catch (error) {
      console.error(error);
    }
  };

  const handleClearAll = async () => {
    try {
      await clearNurseNotifications();
      setNotifications([]);
    } catch (error) {
      console.error(error);
    }
  };

  const unreadCount = notifications.filter((n) => !n.read_at).length;

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-20 bg-slate-200 animate-pulse rounded-2xl" />
        ))}
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div className="flex items-center gap-3">
          <Bell className="w-6 h-6 text-amber-500" />
          <h1 className="text-2xl font-bold text-slate-800 flex items-center gap-2">
            Notifications
            {unreadCount > 0 && (
              <span className="bg-rose-500 text-white text-xs font-bold px-2 py-0.5 rounded-full">
                {unreadCount} New
              </span>
            )}
          </h1>
        </div>
        {notifications.length > 0 && (
          <button
            onClick={handleClearAll}
            className="flex items-center gap-2 px-4 py-2 bg-rose-50 hover:bg-rose-100 text-rose-600 rounded-xl text-sm font-bold transition-colors"
          >
            <Trash2 className="w-4 h-4" /> Clear All
          </button>
        )}
      </div>

      {loadError && (
        <div className="p-3 rounded-xl bg-rose-50 border border-rose-100 text-rose-700 text-sm font-semibold">
          {loadError}
        </div>
      )}

      <div className="space-y-3">
        {notifications.length === 0 && !loadError ? (
          <div className="text-center py-12 bg-white rounded-2xl shadow-sm border border-slate-100 text-slate-500">
            No notifications. You&apos;re all caught up.
          </div>
        ) : (
          <AnimatePresence>
            {notifications.map((notif, i) => (
              <motion.div
                layout
                key={notif.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.97 }}
                transition={{ delay: i * 0.04 }}
                className={`p-4 rounded-2xl border transition-all flex items-start justify-between gap-4 ${
                  notif.read_at ? "bg-slate-50 border-slate-100" : "bg-white border-cyan-200 shadow-sm"
                }`}
              >
                <div>
                  <p className={`text-sm ${notif.read_at ? "text-slate-600" : "font-semibold text-slate-800"}`}>
                    {notif.title}
                  </p>
                  {notif.body && <p className="text-sm text-slate-500 mt-0.5">{notif.body}</p>}
                  <p className="text-xs text-slate-400 mt-1">
                    {notif.created_at ? new Date(notif.created_at).toLocaleString() : ""}
                  </p>
                </div>
                {!notif.read_at && (
                  <button
                    onClick={() => handleMarkRead(notif.id)}
                    className="p-2 text-cyan-600 hover:bg-cyan-50 rounded-xl transition-colors flex-shrink-0"
                    title="Mark as read"
                  >
                    <Check className="w-5 h-5" />
                  </button>
                )}
              </motion.div>
            ))}
          </AnimatePresence>
        )}
      </div>
    </div>
  );
}
