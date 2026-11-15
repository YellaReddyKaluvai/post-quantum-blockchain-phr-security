"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import { Search, User, Loader2, X } from "lucide-react";

interface PatientResult {
  id: string;
  user_id: string;
  full_name: string;
  email: string;
  gender: string;
}

interface PatientSearchSelectProps {
  onSelect: (patient: PatientResult) => void;
  searchFn: (query: string) => Promise<PatientResult[]>;
  placeholder?: string;
  label?: string;
  selectedPatient?: PatientResult | null;
  onClear?: () => void;
}

export default function PatientSearchSelect({
  onSelect,
  searchFn,
  placeholder = "Search by name or Patient ID...",
  label = "Select Patient",
  selectedPatient = null,
  onClear,
}: PatientSearchSelectProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<PatientResult[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Debounced search — waits 300ms after user stops typing
  const handleSearch = useCallback(
    (value: string) => {
      setQuery(value);
      if (debounceRef.current) clearTimeout(debounceRef.current);

      if (value.length < 2) {
        setResults([]);
        setIsOpen(false);
        return;
      }

      setLoading(true);
      debounceRef.current = setTimeout(async () => {
        try {
          const data = await searchFn(value);
          setResults(data);
          setIsOpen(true);
        } catch (err) {
          console.error("Patient search error:", err);
          setResults([]);
        } finally {
          setLoading(false);
        }
      }, 300);
    },
    [searchFn]
  );

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleSelect = (patient: PatientResult) => {
    onSelect(patient);
    setQuery("");
    setResults([]);
    setIsOpen(false);
  };

  const handleClear = () => {
    if (onClear) onClear();
    setQuery("");
    setResults([]);
    setIsOpen(false);
  };

  // If a patient is already selected, show the selection chip
  if (selectedPatient) {
    return (
      <div>
        {label && <label className="block text-sm font-medium text-slate-700 mb-1.5">{label}</label>}
        <div className="flex items-center gap-3 bg-cyan-50 border border-cyan-200 rounded-xl px-4 py-3">
          <div className="w-9 h-9 rounded-full bg-cyan-100 flex items-center justify-center flex-shrink-0">
            <User className="w-4 h-4 text-cyan-600" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-bold text-slate-800 truncate">{selectedPatient.full_name}</p>
            <p className="text-xs text-slate-500 truncate">
              {selectedPatient.user_id || "Pending ID"} • {selectedPatient.email}
            </p>
          </div>
          <button
            type="button"
            onClick={handleClear}
            className="p-1.5 rounded-full hover:bg-cyan-100 text-slate-400 hover:text-slate-600 transition-colors"
            aria-label="Clear selection"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="relative">
      {label && <label className="block text-sm font-medium text-slate-700 mb-1.5">{label}</label>}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
        <input
          type="text"
          value={query}
          onChange={(e) => handleSearch(e.target.value)}
          onFocus={() => results.length > 0 && setIsOpen(true)}
          placeholder={placeholder}
          className="w-full pl-10 pr-10 py-2.5 bg-white border border-slate-200 rounded-xl text-sm focus:ring-2 focus:ring-cyan-500/20 focus:border-cyan-500 outline-none transition-all"
        />
        {loading && (
          <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-cyan-500 animate-spin" />
        )}
      </div>

      {/* Dropdown Results */}
      {isOpen && (
        <div className="absolute z-50 mt-1 w-full bg-white border border-slate-200 rounded-xl shadow-xl max-h-60 overflow-y-auto">
          {results.length === 0 ? (
            <div className="p-4 text-center text-sm text-slate-500">
              No patients found matching &quot;{query}&quot;
            </div>
          ) : (
            results.map((patient) => (
              <button
                key={patient.id}
                type="button"
                onClick={() => handleSelect(patient)}
                className="w-full flex items-center gap-3 px-4 py-3 hover:bg-cyan-50 transition-colors text-left border-b border-slate-50 last:border-0"
              >
                <div className="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center flex-shrink-0">
                  <User className="w-4 h-4 text-slate-500" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-slate-800 truncate">{patient.full_name}</p>
                  <p className="text-xs text-slate-500 truncate">
                    {patient.user_id || "Pending ID"} • {patient.gender}
                  </p>
                </div>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
