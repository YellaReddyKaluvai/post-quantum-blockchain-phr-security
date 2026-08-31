"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { Shield, Menu, X, Hexagon } from "lucide-react";

export default function Navbar() {
  const [scrolled, setScrolled] = useState(false);
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 20);
    };
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  return (
    <motion.nav
      initial={{ y: -100 }}
      animate={{ y: 0 }}
      transition={{ duration: 0.8, ease: "easeOut" }}
      className={`fixed top-0 w-full z-50 transition-all duration-300 ${
        scrolled
          ? "bg-white/80 backdrop-blur-lg border-b border-slate-200/80 shadow-sm"
          : "bg-transparent"
      }`}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-20">
          <div className="flex items-center gap-2">
            <div className="relative flex items-center justify-center w-10 h-10">
              <Hexagon className="absolute text-cyan-500 w-full h-full animate-[spin_10s_linear_infinite]" strokeWidth={1} />
              <Shield className="relative text-cyan-700 w-5 h-5" />
            </div>
            <span className="text-xl font-bold tracking-widest text-slate-800">
              Quantum<span className="text-cyan-500">.</span>Care
            </span>
          </div>
          
          <div className="hidden md:block">
            <div className="ml-10 flex items-baseline space-x-8">
              {['Technology', 'Platform', 'Security', 'Company'].map((item) => (
                <Link
                  key={item}
                  href="#"
                  className="text-slate-600 hover:text-cyan-600 px-3 py-2 rounded-md font-medium text-sm transition-colors relative group"
                >
                  {item}
                  <span className="absolute -bottom-1 left-0 w-0 h-0.5 bg-cyan-500 transition-all group-hover:w-full" />
                </Link>
              ))}
            </div>
          </div>
          
          <div className="hidden md:flex items-center gap-6">
            <Link 
              href="/signup"
              className="text-slate-600 hover:text-cyan-600 font-medium text-sm transition-colors"
            >
              Sign Up
            </Link>
            <Link 
              href="/login"
              className="relative inline-flex h-10 overflow-hidden rounded-full p-[1px] focus:outline-none focus:ring-2 focus:ring-cyan-400 focus:ring-offset-2 focus:ring-offset-white"
            >
              <span className="absolute inset-[-1000%] animate-[spin_2s_linear_infinite] bg-[conic-gradient(from_90deg_at_50%_50%,#a5f3fc_0%,#0891b2_50%,#a5f3fc_100%)]" />
              <span className="inline-flex h-full w-full cursor-pointer items-center justify-center rounded-full bg-white px-6 py-1 text-sm font-medium text-cyan-700 backdrop-blur-3xl transition-all hover:bg-cyan-50">
                Login
              </span>
            </Link>
          </div>
          
          {/* Mobile menu button */}
          <div className="md:hidden flex items-center">
            <button
              onClick={() => setIsOpen(!isOpen)}
              className="text-slate-500 hover:text-slate-800 focus:outline-none p-2"
            >
              {isOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
            </button>
          </div>
        </div>
      </div>
      
      {/* Mobile Menu */}
      {isOpen && (
        <motion.div 
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          className="md:hidden bg-white border-b border-slate-200"
        >
          <div className="px-2 pt-2 pb-3 space-y-1 sm:px-3">
            {['Technology', 'Platform', 'Security', 'Company'].map((item) => (
              <Link
                key={item}
                href="#"
                className="text-slate-600 hover:text-cyan-600 block px-3 py-2 rounded-md text-base font-medium"
              >
                {item}
              </Link>
            ))}
            <Link 
              href="/signup"
              className="block w-full text-center mt-4 border border-cyan-200 text-cyan-700 font-medium py-2 rounded-md transition-colors"
            >
              Sign Up
            </Link>
            <Link 
              href="/login"
              className="block w-full text-center mt-2 bg-cyan-600 hover:bg-cyan-500 text-white font-medium py-2 rounded-md transition-colors"
            >
              Login
            </Link>
          </div>
        </motion.div>
      )}
    </motion.nav>
  );
}
