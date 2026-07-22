"use client";

import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Bell, Check, Trash2, Info, AlertTriangle, CheckCircle, Clock } from "lucide-react";
import { getPatientNotifications, markNotificationRead, clearNotifications } from "@/lib/session";

export default function NotificationsPage() {
  const [loading, setLoading] = useState(true);
  const [notifications, setNotifications] = useState<any[]>([]);

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    try {
      const data = await getPatientNotifications();
      setNotifications(data);
    } catch (error) {
      console.error("Failed to load notifications:", error);
    } finally {
      setLoading(false);
    }
  }

  const handleMarkRead = async (id: string) => {
    try {
      await markNotificationRead(id);
      setNotifications(notifications.map(n => n.id === id ? { ...n, is_read: true } : n));
    } catch (error) {
      console.error("Failed to mark notification read:", error);
    }
  };

  const handleClearAll = async () => {
    try {
      await clearNotifications();
      setNotifications([]);
    } catch (error) {
      console.error("Failed to clear notifications:", error);
    }
  };

  const getIcon = (type: string) => {
    switch (type?.toLowerCase()) {
      case "alert": return <AlertTriangle className="w-5 h-5 text-amber-500" />;
      case "success": return <CheckCircle className="w-5 h-5 text-emerald-500" />;
      case "reminder": return <Clock className="w-5 h-5 text-blue-500" />;
      default: return <Info className="w-5 h-5 text-cyan-500" />;
    }
  };

  if (loading) {
    return (
      <div className="space-y-6 max-w-3xl mx-auto">
        <div className="h-8 w-48 bg-slate-200 animate-pulse rounded-md"></div>
        <div className="space-y-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="bg-white rounded-2xl h-24 animate-pulse shadow-sm border border-slate-100"></div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="flex justify-between items-end">
        <div>
          <h1 className="text-xl md:text-2xl font-bold text-slate-800">Notifications</h1>
          <p className="text-slate-500 mt-1">Stay updated on your health records and appointments.</p>
        </div>
        {notifications.length > 0 && (
          <button
            onClick={handleClearAll}
            className="flex items-center gap-2 px-4 py-2 bg-white border border-slate-200 rounded-xl text-sm font-semibold text-rose-600 hover:bg-rose-50 hover:border-rose-100 transition-colors shadow-sm"
          >
            <Trash2 className="w-4 h-4" /> Clear All
          </button>
        )}
      </motion.div>

      {notifications.length === 0 ? (
        <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-12 text-center">
          <div className="w-16 h-16 bg-slate-50 rounded-full flex items-center justify-center mx-auto mb-4">
            <Bell className="w-8 h-8 text-slate-300" />
          </div>
          <h3 className="text-lg font-bold text-slate-700">All Caught Up</h3>
          <p className="text-slate-500 mt-1">You have no new notifications.</p>
        </div>
      ) : (
        <div className="space-y-3">
          <AnimatePresence>
            {notifications.map((notification, index) => (
              <motion.div
                layout
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, scale: 0.95 }}
                transition={{ delay: index * 0.05 }}
                key={notification.id}
                className={`bg-white rounded-2xl shadow-sm border relative overflow-hidden transition-colors ${!notification.is_read ? "border-cyan-100 bg-cyan-50/10" : "border-slate-100"}`}
              >
                {!notification.is_read && (
                  <div className="absolute top-0 left-0 w-1 h-full bg-cyan-400"></div>
                )}
                <div className="p-4 sm:p-5 flex gap-4">
                  <div className="flex-shrink-0 mt-1">
                    <div className="p-2.5 bg-white shadow-sm border border-slate-100 rounded-full">
                      {getIcon(notification.type)}
                    </div>
                  </div>
                  <div className="flex-1">
                    <div className="flex justify-between items-start gap-4">
                      <h3 className={`text-base font-bold ${!notification.is_read ? "text-slate-900" : "text-slate-700"}`}>
                        {notification.title}
                      </h3>
                      <span className="text-xs font-medium text-slate-400 whitespace-nowrap">
                        {new Date(notification.timestamp).toLocaleDateString()}
                      </span>
                    </div>
                    <p className={`text-sm mt-1 mb-3 ${!notification.is_read ? "text-slate-700 font-medium" : "text-slate-500"}`}>
                      {notification.body}
                    </p>
                    
                    {!notification.is_read && (
                      <button
                        onClick={() => handleMarkRead(notification.id)}
                        className="flex items-center gap-1.5 text-xs font-bold text-cyan-600 hover:text-cyan-700 transition-colors"
                      >
                        <Check className="w-3.5 h-3.5" /> Mark as read
                      </button>
                    )}
                  </div>
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
}
