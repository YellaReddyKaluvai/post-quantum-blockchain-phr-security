"use client";

import React from "react";
import { motion, Variants } from "framer-motion";
import { Lock, Cpu, Database, Network, PlayCircle, Clock, Captions } from "lucide-react";
import Navbar from "@/components/Navbar";
import Link from "next/link";

export default function LandingPage() {
  const container: Variants = {
    hidden: { opacity: 0 },
    show: {
      opacity: 1,
      transition: { staggerChildren: 0.15 }
    }
  };

  const item: Variants = {
    hidden: { opacity: 0, y: 30 },
    show: { opacity: 1, y: 0, transition: { duration: 0.7, ease: "easeOut" } }
  };

  const features = [
    {
      icon: Lock,
      title: "Lattice Cryptography",
      desc: "ML-KEM-768 and ML-DSA-65 protect report keys and verify signatures.",
      color: "text-cyan-600",
      iconBg: "bg-gradient-to-br from-cyan-400 to-sky-500",
      borderTop: "border-t-4 border-t-cyan-400",
      shadow: "hover:shadow-cyan-100",
    },
    {
      icon: Database,
      title: "Encrypted Records",
      desc: "Encrypted reports are stored in PostgreSQL. IPFS publishing is an optional integration.",
      color: "text-teal-600",
      iconBg: "bg-gradient-to-br from-teal-400 to-emerald-500",
      borderTop: "border-t-4 border-t-teal-400",
      shadow: "hover:shadow-teal-100",
    },
    {
      icon: Network,
      title: "Auditable Access",
      desc: "Trace clinical actions through audit logs. Live blockchain anchoring is not enabled in this demo.",
      color: "text-emerald-600",
      iconBg: "bg-gradient-to-br from-emerald-400 to-green-500",
      borderTop: "border-t-4 border-t-emerald-400",
      shadow: "hover:shadow-emerald-100",
    },
    {
      icon: Cpu,
      title: "AI Diagnostic Ready",
      desc: "Securely share strictly permissioned datasets with AI models.",
      color: "text-violet-600",
      iconBg: "bg-gradient-to-br from-violet-400 to-purple-500",
      borderTop: "border-t-4 border-t-violet-400",
      shadow: "hover:shadow-violet-100",
    },
  ];

  return (
    <>
      <Navbar />

      {/* Hero Section */}
      <main className="flex-1 flex flex-col items-center justify-center pt-32 pb-20 px-4 sm:px-6 lg:px-8 relative z-10">

        {/* Grid Background */}
        <div className="absolute inset-0 z-[-1] bg-[linear-gradient(to_right,#0891b215_1px,transparent_1px),linear-gradient(to_bottom,#0891b215_1px,transparent_1px)] bg-[size:32px_32px] [mask-image:radial-gradient(ellipse_70%_60%_at_50%_0%,#000_70%,transparent_100%)]" />

        {/* Decorative floating blob */}
        <div className="absolute top-24 left-1/4 w-72 h-72 bg-cyan-200/30 rounded-full blur-3xl pointer-events-none float-anim" />
        <div className="absolute top-40 right-1/4 w-56 h-56 bg-emerald-200/30 rounded-full blur-3xl pointer-events-none float-anim" style={{ animationDelay: "1.5s" }} />

        <motion.div
          className="text-center max-w-5xl mx-auto"
          variants={container}
          initial="hidden"
          animate="show"
        >
          {/* Badge */}
          <motion.div
            variants={item}
            className="inline-flex items-center gap-2 px-5 py-2 rounded-full border border-cyan-200 bg-white text-cyan-700 text-sm font-semibold mb-10 badge-glow shadow-sm"
          >
            <span className="flex h-2.5 w-2.5 rounded-full bg-cyan-500 pulse-glow" />
            ML-KEM-768 + ML-DSA-65 Post-Quantum Security
          </motion.div>

          {/* Main Headline */}
          <motion.h1
            variants={item}
            className="text-5xl md:text-7xl font-extrabold tracking-tight mb-6"
          >
            <span className="block text-slate-800">
              The Future of Health Privacy
            </span>
            <span className="block text-shimmer mt-2 pb-2">
              Powered by Quantum Security.
            </span>
          </motion.h1>

          {/* Subtext */}
          <motion.p
            variants={item}
            className="mt-4 text-xl text-slate-500 max-w-3xl mx-auto mb-12 leading-relaxed"
          >
            Explore a Personal Health Record (PHR) platform that connects patients
            and care teams with consent-based access, encrypted reports and
            post-quantum signatures.
          </motion.p>

          {/* CTA Buttons */}
          <motion.div
            variants={item}
            className="flex flex-col sm:flex-row gap-4 justify-center items-center"
          >
            <a
              href="#project-demo"
              className="inline-flex items-center justify-center gap-2 px-8 py-4 bg-slate-900 text-white font-bold rounded-2xl hover:bg-slate-700 transition-colors w-full sm:w-auto focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-cyan-600"
            >
              <PlayCircle className="h-5 w-5" aria-hidden="true" />
              Watch Project Demo
            </a>
            <Link
              href="/signup"
              className="px-9 py-4 bg-gradient-to-r from-cyan-500 to-teal-500 text-white font-bold rounded-2xl hover:from-cyan-600 hover:to-teal-600 transition-all w-full sm:w-auto text-center glow-teal shadow-lg hover:-translate-y-1 hover:scale-105"
            >
              Access Patient Portal (Sign Up)
            </Link>
            <Link
              href="/login"
              className="px-9 py-4 bg-white border-2 border-slate-200 text-slate-700 font-bold rounded-2xl hover:border-cyan-300 hover:text-cyan-700 hover:bg-cyan-50 hover:-translate-y-1 hover:scale-105 transition-all w-full sm:w-auto text-center shadow-sm"
            >
              Login
            </Link>
          </motion.div>
        </motion.div>

        <section
          id="project-demo"
          aria-labelledby="project-demo-title"
          className="scroll-mt-24 mt-20 w-full max-w-6xl overflow-hidden rounded-3xl border border-cyan-200 bg-white shadow-xl shadow-cyan-900/10"
        >
          <div className="grid lg:grid-cols-[0.8fr_1.2fr]">
            <div className="p-6 sm:p-9 lg:p-10 flex flex-col justify-center">
              <span className="inline-flex items-center gap-2 self-start rounded-full bg-cyan-50 px-3 py-1 text-xs font-bold uppercase tracking-wider text-cyan-800">
                <PlayCircle className="h-4 w-4" aria-hidden="true" />
                Project demonstration
              </span>
              <h2 id="project-demo-title" className="mt-5 text-3xl sm:text-4xl font-extrabold tracking-tight text-slate-900">
                See QuantumCare in action
              </h2>
              <p className="mt-4 text-slate-600 leading-relaxed">
                Follow a patient&apos;s journey from consent and clinical care to a
                signed lab report. Tour the patient, doctor, nurse, laboratory and
                administrator portals in this recorded walkthrough of the live app.
              </p>
              <div className="mt-5 flex flex-wrap gap-x-5 gap-y-2 text-sm font-medium text-slate-700">
                <span className="inline-flex items-center gap-2"><Clock className="h-4 w-4 text-cyan-700" aria-hidden="true" />3 min 59 sec</span>
                <span className="inline-flex items-center gap-2"><Captions className="h-4 w-4 text-cyan-700" aria-hidden="true" />Explanations on screen</span>
              </div>
              <p id="project-demo-description" className="mt-5 text-sm text-slate-500 leading-relaxed">
                Free to watch, no sign-in needed. Captions are built into the video;
                there is no spoken audio. All demonstration records are fictional.
              </p>
              <a href="/demo/quantumcare-demo-transcript.txt" className="mt-5 self-start text-sm font-semibold text-cyan-800 underline underline-offset-4 hover:text-cyan-600">
                Read the full video transcript
              </a>
            </div>
            <div className="flex items-center bg-slate-950 p-3 sm:p-5">
              <video
                controls
                playsInline
                preload="none"
                poster="/demo/quantumcare-demo-poster.jpg"
                aria-label="QuantumCare project demonstration with embedded explanatory captions"
                aria-describedby="project-demo-description"
                className="aspect-[4/3] w-full rounded-xl bg-slate-950"
                width={1440}
                height={1080}
              >
                <source src="/demo/quantumcare-captioned-demo.mp4" type="video/mp4" />
                Your browser does not support embedded video. <a href="/demo/quantumcare-captioned-demo.mp4">Open the project demo video</a>.
              </video>
            </div>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between border-t border-cyan-100 bg-cyan-50/60 px-6 py-4 sm:px-9">
            <p className="text-sm text-slate-600">Core workflow, security checks and measured results • Recorded 25 October 2026</p>
            <a href="/demo/quantumcare-captioned-demo.mp4" className="shrink-0 text-sm font-semibold text-cyan-800 underline underline-offset-4 hover:text-cyan-600">Open video in full size</a>
          </div>
        </section>

        {/* ── Feature Cards ─────────────────────────────────── */}
        <motion.div
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8 mt-20 max-w-7xl mx-auto w-full"
          variants={container}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, margin: "-100px" }}
        >
          {features.map((feature, i) => (
            <motion.div
              key={i}
              variants={item}
              className={`card-3d gradient-border-card p-7 ${feature.borderTop} ${feature.shadow} hover:shadow-2xl transition-shadow`}
            >
              {/* Floating icon */}
              <div className={`w-14 h-14 rounded-2xl ${feature.iconBg} flex items-center justify-center mb-6 text-white shadow-lg float-anim`}
                style={{ animationDelay: `${i * 0.4}s` }}
              >
                <feature.icon className="w-7 h-7 drop-shadow-sm" />
              </div>

              <h3 className={`text-lg font-bold ${feature.color} mb-2 tracking-tight`}>
                {feature.title}
              </h3>
              <p className="text-slate-500 text-sm leading-relaxed">
                {feature.desc}
              </p>

              {/* Bottom accent bar */}
              <div className="mt-6 h-1 w-12 rounded-full bg-gradient-to-r from-cyan-400 to-teal-400 opacity-60" />
            </motion.div>
          ))}
        </motion.div>
      </main>
    </>
  );
}
