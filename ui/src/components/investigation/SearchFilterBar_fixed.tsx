"use client";

import React, { useCallback, useRef, useState, useEffect } from "react";
import Image from "next/image";
import { useInvestigation } from "./InvestigationContext";
import type { ClothingClass, ClothingColor } from "@/types";

// ─── Constants ───────────────────────────────────────────────

const CLOTHING_OPTIONS: ClothingClass[] = [
  "short sleeve top",
  "long sleeve top",
  "short sleeve outwear",
  "long sleeve outwear",
  "vest",
  "sling",
  "shorts",
  "trousers",
  "skirt",
  "short sleeve dress",
  "long sleeve dress",
  "vest dress",
  "sling dress",
];

const COLOR_OPTIONS: { value: ClothingColor; hex: string; label: string }[] = [
  { value: "Red",    hex: "#ef4444", label: "RED" },
  { value: "Orange", hex: "#f97316", label: "ORG" },
  { value: "Yellow", hex: "#eab308", label: "YEL" },
  { value: "Green",  hex: "#22c55e", label: "GRN" },
  { value: "Blue",   hex: "#3b82f6", label: "BLU" },
  { value: "Navy",   hex: "#1e3a5f", label: "NAV" },
  { value: "Purple", hex: "#a855f7", label: "PUR" },
  { value: "Pink",   hex: "#ec4899", label: "PNK" },
  { value: "White",  hex: "#f8fafc", label: "WHT" },
  { value: "Gray",   hex: "#6b7280", label: "GRY" },
  { value: "Brown",  hex: "#92400e", label: "BRN" },
  { value: "Black",  hex: "#0f172a", label: "BLK" },
];

const MOCK_CAMERAS = [
  { id: "CAM-01", name: "Main Entrance" },
  { id: "CAM-02", name: "Corridor B" },
  { id: "CAM-03", name: "Parking Lot" },
  { id: "CAM-04", name: "Exit Gate" },
];

// ─── Component ───────────────────────────────────────────────

export default function SearchFilterBar() {
  const { state, toggleClothing, toggleColor, setLogic, setThreshold, setCamera, setTimeRange, resetFilters, runSearch, submitAutoFill, clearAutoFill } =
    useInvestigation();
  const { filters, autoFillImage, autoFillStatus, autoFillResult, isSearching } = state;

  const [isDragOver, setIsDragOver] = useState(false);
  const [showTimeExpanded, setShowTimeExpanded] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── Drag & Drop ──────────────────────────────────────────────
  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file && file.type.startsWith("image/")) submitAutoFill(file);
    },
    [submitAutoFill]
  );

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) submitAutoFill(file);
    e.target.value = "";
  };

  // ── Auto search on filter change ───────────────────────
  useEffect(() => {
    if (filters.clothing.length > 0 || filters.colors.length > 0) {
      const timer = setTimeout(() => {
        runSearch();
      }, 300); // Debounce 300ms
      
      return () => clearTimeout(timer);
    }
  }, [filters.clothing, filters.colors, filters.logic, filters.threshold, filters.camera_id, filters.start_time, filters.end_time]);

  const activeFilterCount =
    filters.clothing.length + filters.colors.length +
    (filters.camera_id ? 1 : 0) +
    (filters.start_time ? 1 : 0);

  return (
    <div className="hud-panel p-3 flex flex-col gap-3">
      {/* ── Row 1: AutoFill + Clothing + Logic ── */}
      <div className="flex gap-3 items-start">
        {/* ── Image Auto-Fill Zone ── */}
        <div className="flex-shrink-0">
          <SectionLabel>AUTO-FILL</SectionLabel>
          <div
            className={`
              relative w-28 h-[84px] rounded-sm border-2 border-dashed cursor-pointer
              flex flex-col items-center justify-center gap-1 transition-all duration-200 overflow-hidden
              ${isDragOver
                ? "border-pink-400 bg-pink-950/30 scale-[1.02]"
                : autoFillImage
                ? "border-cyan-500/60 bg-slate-900/60"
                : "border-slate-700 bg-slate-900/30 hover:border-slate-600 hover:bg-slate-900/50"
              }
            `}
            onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
            onDragLeave={() => setIsDragOver(false)}
            onDrop={handleDrop}
            onClick={() => !autoFillImage && fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={handleFileChange}
            />

            {/* States */}
            {autoFillImage ? (
              <>
                <Image src={autoFillImage} alt="Target" fill className="object-cover opacity-70" />
                <div className="absolute inset-0 bg-slate-950/40" />
                {/* Status overlay */}
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-1 z-10">
                  {autoFillStatus === "analyzing" && <AnalyzingOverlay />}
                  {autoFillStatus === "done" && autoFillResult && (
                    <DoneOverlay result={autoFillResult} />
                  )}
                  {autoFillStatus === "error" && (
                    <div className="font-mono text-[8px] text-red-400 text-center px-1">ANALYSIS FAILED</div>
                  )}
                </div>
                {/* Clear button */}
                <button
                  className="absolute top-1 right-1 z-20 w-4 h-4 rounded-full bg-slate-900/80 border border-slate-700 flex items-center justify-center hover:border-red-500/60 hover:text-red-400 text-slate-500 transition-colors"
                  onClick={(e) => { e.stopPropagation(); clearAutoFill(); }}
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} className="w-2 h-2">
                    <path d="M18 6L6 18M6 6l12 12" />
                  </svg>
                </button>
              </>
            ) : (
              <>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}
                  className={`w-5 h-5 transition-colors ${isDragOver ? "text-pink-400" : "text-slate-600"}`}
                >
                  <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12" />
                </svg>
                <span className={`font-mono text-[8px] text-center leading-tight px-1 transition-colors ${isDragOver ? "text-pink-400" : "text-slate-600"}`}>
                  {isDragOver ? "RELEASE TO ANALYZE" : "DROP TARGET\nIMAGE"}
                </span>
              </>
            )}
          </div>
        </div>

        {/* ── Clothing Chips ── */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between mb-1.5">
            <SectionLabel>CLOTHING TYPE</SectionLabel>
            {/* Logic switch */}
            <div className="flex items-center gap-1 bg-slate-900/60 border border-slate-800 rounded-sm p-0.5">
              {(["OR", "AND"] as const).map((l) => (
                <button
                  key={l}
                  onClick={() => setLogic(l)}
                  className={`
                    px-2 py-0.5 rounded-sm font-mono text-[8px] tracking-wider transition-all
                    ${filters.logic === l
                      ? "bg-cyan-900/60 text-cyan-400 border border-cyan-700/60"
                      : "text-slate-600 hover:text-slate-400"
                    }
                  `}
                >
                  {l}
                </button>
              ))}
            </div>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {CLOTHING_OPTIONS.map((item) => {
              const active = filters.clothing.includes(item);
              const isAutoFilled = autoFillResult?.class === item && autoFillStatus === "done";
              return (
                <button
                  key={item}
                  onClick={() => toggleClothing(item)}
                  className={`
                    relative chip transition-all
                    ${active ? "active" : ""}
                    ${isAutoFilled ? "ring-1 ring-pink-500/60" : ""}
                  `}
                >
                  {item}
                  {isAutoFilled && (
                    <span className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-pink-500 border border-slate-950 animate-pulse" />
                  )}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* ── Row 2: Color Matrix + Threshold ── */}
      <div className="flex gap-3 items-start">
        {/* Color Grid */}
        <div className="flex-1">
          <SectionLabel>COLOR MATRIX</SectionLabel>
          <div className="flex flex-wrap gap-1.5 mt-1">
            {COLOR_OPTIONS.map(({ value, hex, label }) => {
              const active = filters.colors.includes(value);
              const isAutoFilled = (autoFillResult?.color === value || autoFillResult?.secondary_color === value) && autoFillStatus === "done";
              return (
                <button
                  key={value}
                  onClick={() => toggleColor(value)}
                  title={value}
                  className={`
                    relative flex items-center gap-1.5 px-2 py-1 rounded-sm border font-mono text-[9px]
                    transition-all duration-150
                    ${active
                      ? "border-white/30 bg-white/5 text-white shadow-sm"
                      : "border-slate-800 text-slate-600 hover:border-slate-600 hover:text-slate-400"
                    }
                    ${isAutoFilled ? "ring-1 ring-pink-500/60" : ""}
                  `}
                  style={active ? { borderColor: hex + "60", boxShadow: `0 0 8px ${hex}30` } : {}}
                >
                  {/* Color swatch */}
                  <span
                    className={`w-3 h-3 rounded-full border flex-shrink-0 transition-all ${active ? "scale-110" : "scale-90"}`}
                    style={{
                      background: hex,
                      borderColor: active ? hex : "rgba(255,255,255,0.1)",
                      boxShadow: active ? `0 0 6px ${hex}80` : "none",
                    }}
                  />
                  <span style={active ? { color: hex } : {}}>{label}</span>
                  {isAutoFilled && (
                    <span className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-pink-500 border border-slate-950 animate-pulse" />
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* Threshold Slider */}
        <div className="flex-shrink-0 w-40">
          <SectionLabel>COLOR TOLERANCE</SectionLabel>
          <div className="mt-2 px-1">
            <input
              type="range"
              min={0.4}
              max={1.0}
              step={0.05}
              value={filters.threshold}
              onChange={(e) => setThreshold(parseFloat(e.target.value))}
              className="w-full h-1 appearance-none bg-slate-800 rounded-full outline-none cursor-pointer
                [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3
                [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-cyan-400
                [&::-webkit-slider-thumb]:shadow-[0_0_6px_rgba(0,245,255,0.6)]
                [&::-webkit-slider-thumb]:cursor-pointer"
            />
            <div className="flex justify-between mt-1">
              <span className="font-mono text-[7px] text-slate-600">LOOSE</span>
              <span className="font-mono text-[9px] text-cyan-400">{Math.round(filters.threshold * 100)}%</span>
              <span className="font-mono text-[7px] text-slate-600">STRICT</span>
            </div>
          </div>

          {/* Camera select */}
          <div className="mt-3">
            <SectionLabel>CAMERA</SectionLabel>
            <select
              value={filters.camera_id ?? ""}
              onChange={(e) => setCamera(e.target.value || undefined)}
              className="w-full mt-1 bg-slate-900/60 border border-slate-700/60 rounded-sm px-2 py-1
                font-mono text-[10px] text-slate-300 outline-none focus:border-cyan-700/60
                cursor-pointer appearance-none"
            >
              <option value="">ALL CAMERAS</option>
              {MOCK_CAMERAS.map((c) => (
                <option key={c.id} value={c.id}>{c.id} · {c.name}</option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* ── Row 3: Time range (collapsible) + Actions ── */}
      <div className="flex items-center gap-3 pt-1 border-t border-slate-800/60">
        {/* Time toggle */}
        <button
          onClick={() => setShowTimeExpanded((s) => !s)}
          className="flex items-center gap-1.5 font-mono text-[9px] text-slate-500 hover:text-slate-300 transition-colors"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-3.5 h-3.5">
            <circle cx="12" cy="12" r="10" /><path d="M12 6v6l4 2" />
          </svg>
          TIME RANGE
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}
            className={`w-3 h-3 transition-transform ${showTimeExpanded ? "rotate-180" : ""}`}>
            <path d="M6 9l6 6 6-6" />
          </svg>
        </button>

        {showTimeExpanded && (
          <div className="flex items-center gap-2 flex-1">
            <input
              type="datetime-local"
              value={filters.start_time?.slice(0, 16) ?? ""}
              onChange={(e) => setTimeRange(e.target.value ? new Date(e.target.value).toISOString() : undefined, filters.end_time)}
              className="bg-slate-900/60 border border-slate-700/60 rounded-sm px-2 py-1
                font-mono text-[9px] text-slate-300 outline-none focus:border-cyan-700/60"
            />
            <span className="font-mono text-[9px] text-slate-600">→</span>
            <input
              type="datetime-local"
              value={filters.end_time?.slice(0, 16) ?? ""}
              onChange={(e) => setTimeRange(filters.start_time, e.target.value ? new Date(e.target.value).toISOString() : undefined)}
              className="bg-slate-900/60 border border-slate-700/60 rounded-sm px-2 py-1
                font-mono text-[9px] text-slate-300 outline-none focus:border-cyan-700/60"
            />
          </div>
        )}

        {/* Active filter summary */}
        {activeFilterCount > 0 && (
          <div className="flex items-center gap-1.5 ml-auto">
            <span className="font-mono text-[8px] text-slate-600">
              {activeFilterCount} FILTER{activeFilterCount !== 1 ? "S" : ""} ACTIVE
            </span>
            <button
              onClick={resetFilters}
              className="font-mono text-[8px] text-red-600 hover:text-red-400 transition-colors underline underline-offset-2"
            >
              CLEAR
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Sub-components ───────────────────────────────────────────

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="font-mono text-[8px] text-slate-600 tracking-[0.2em] mb-1 uppercase">
      {children}
    </div>
  );
}

function Spinner() {
  return (
    <svg className="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
    </svg>
  );
}

function AnalyzingOverlay() {
  return (
    <div className="flex flex-col items-center gap-1">
      <div className="relative w-6 h-6">
        <div className="absolute inset-0 border border-cyan-500/60 animate-ping rounded-full" />
        <div className="absolute inset-1 border border-cyan-400 rounded-full" />
      </div>
      <span className="font-mono text-[7px] text-cyan-400 tracking-widest">ANALYZING</span>
      <div className="progress-bar w-14 mt-0.5" />
    </div>
  );
}

function DoneOverlay({ result }: { result: { class: string; color: string; confidence: number } }) {
  return (
    <div className="flex flex-col items-center gap-0.5 bg-slate-950/70 rounded-sm px-2 py-1.5 w-full mx-1">
      <svg viewBox="0 0 24 24" fill="none" stroke="#39ff14" strokeWidth={2.5} className="w-4 h-4">
        <path d="M20 6L9 17l-5-5" />
      </svg>
      <span className="font-mono text-[8px] text-green-400 font-bold">{result.class}</span>
      <span className="font-mono text-[7px] text-slate-400">{result.color}</span>
      <span className="font-mono text-[7px] text-cyan-600">{Math.round(result.confidence * 100)}%</span>
    </div>
  );
}
