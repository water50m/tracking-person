"use client";

import React, { useCallback, useRef, useState } from "react";
import type { UploadJob, JobStatus } from "@/types";

// ─── Constants ────────────────────────────────────────────────

const ACCEPTED_TYPES = ["video/mp4", "video/avi", "video/x-msvideo", "video/quicktime", "video/x-matroska"];
const ACCEPTED_EXTS = ".mp4,.avi,.mov,.mkv";
const MAX_SIZE_GB = 2;
const MAX_SIZE_BYTES = MAX_SIZE_GB * 1024 * 1024 * 1024;

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}

function statusLabel(s: JobStatus): string {
  return { queued: "QUEUED", processing: "PROCESSING", done: "COMPLETE", error: "ERROR" }[s];
}

const STATUS_STYLE: Record<JobStatus, { text: string; border: string; bg: string; barColor: string }> = {
  queued:     { text: "text-slate-400",  border: "border-slate-700",   bg: "bg-slate-800/40",   barColor: "#64748b" },
  processing: { text: "text-cyan-400",   border: "border-cyan-800/60", bg: "bg-cyan-950/30",    barColor: "#00f5ff" },
  done:       { text: "text-green-400",  border: "border-green-800/60",bg: "bg-green-950/30",   barColor: "#39ff14" },
  error:      { text: "text-red-400",    border: "border-red-800/60",  bg: "bg-red-950/30",     barColor: "#ef4444" },
};

// ─── Component ────────────────────────────────────────────────

export default function UploadTab() {
  const [isDragOver, setIsDragOver] = useState(false);
  const [dragError, setDragError] = useState<string | null>(null);
  const [cameraId, setCameraId] = useState("");
  const [cameraIdError, setCameraIdError] = useState<string | null>(null);
  const [jobs, setJobs] = useState<UploadJob[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── Validate file ──────────────────────────────────────────
  const validateFile = useCallback((file: File): string | null => {
    if (!ACCEPTED_TYPES.includes(file.type) && !file.name.match(/\.(mp4|avi|mov|mkv)$/i)) {
      return `Unsupported format: ${file.name}. Accepted: MP4, AVI, MOV, MKV`;
    }
    if (file.size > MAX_SIZE_BYTES) {
      return `File too large: ${formatBytes(file.size)}. Max ${MAX_SIZE_GB}GB`;
    }
    return null;
  }, []);

  // ── Queue a file ───────────────────────────────────────────
  const queueFile = useCallback(
    async (file: File) => {
      const fileErr = validateFile(file);
      if (fileErr) { setDragError(fileErr); return; }

      if (!cameraId.trim()) {
        setCameraIdError("Camera ID is required before uploading");
        return;
      }

      const jobId = `job-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
      const newJob: UploadJob = {
        job_id: jobId,
        status: "queued",
        camera_id: cameraId.trim().toUpperCase(),
        filename: file.name,
        size_bytes: file.size,
        progress: 0,
      };

      setJobs((prev) => [newJob, ...prev]);

      // Simulate upload + processing
      await simulateUpload(jobId, file, cameraId.trim().toUpperCase(), setJobs);
    },
    [cameraId, validateFile]
  );

  // ── Drag & Drop handlers ───────────────────────────────────
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
    setDragError(null);
  };
  const handleDragLeave = () => setIsDragOver(false);
  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    const files = Array.from(e.dataTransfer.files);
    for (const f of files) await queueFile(f);
  };
  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    for (const f of files) await queueFile(f);
    e.target.value = "";
  };

  const removeJob = (id: string) =>
    setJobs((prev) => prev.filter((j) => j.job_id !== id));

  const retryJob = (id: string) =>
    setJobs((prev) =>
      prev.map((j) => j.job_id === id ? { ...j, status: "queued", progress: 0, error: undefined } : j)
    );

  return (
    <div className="flex gap-4 h-full min-h-0">
      {/* ── Left: Drop zone + form ── */}
      <div className="flex-1 flex flex-col gap-4 min-w-0">

        {/* Camera ID input */}
        <div className="hud-panel p-4">
          <label className="font-mono text-[8px] text-slate-500 tracking-[0.2em] uppercase block mb-2">
            CAMERA ID <span className="text-red-500">*</span>
          </label>
          <div className="flex gap-3 items-start">
            <div className="flex-1">
              <input
                type="text"
                value={cameraId}
                onChange={(e) => {
                  setCameraId(e.target.value);
                  setCameraIdError(null);
                }}
                placeholder="e.g. CAM-01"
                maxLength={20}
                data-camera-id
                className={`
                  w-full bg-slate-900/60 border rounded-sm px-3 py-2 font-mono text-sm
                  text-slate-200 placeholder-slate-700 outline-none tracking-wider uppercase
                  transition-colors
                  ${cameraIdError
                    ? "border-red-700/60 focus:border-red-500/60"
                    : "border-slate-700/60 focus:border-yellow-600/60"
                  }
                `}
              />
              {cameraIdError && (
                <p className="font-mono text-[9px] text-red-400 mt-1 tracking-wide">{cameraIdError}</p>
              )}
            </div>
            <div className="font-mono text-[8px] text-slate-600 pt-2 leading-relaxed">
              <p>Assign this video to a camera.</p>
              <p>All detections will be tagged with this ID.</p>
            </div>
          </div>

          {/* Quick-fill presets */}
          <div className="flex items-center gap-2 mt-2">
            <span className="font-mono text-[8px] text-slate-700">QUICK:</span>
            {["CAM-01", "CAM-02", "CAM-03", "CAM-04"].map((id) => (
              <button
                key={id}
                onClick={() => { setCameraId(id); setCameraIdError(null); }}
                className={`font-mono text-[8px] px-2 py-0.5 rounded-sm border transition-colors
                  ${cameraId === id
                    ? "border-yellow-600/60 text-yellow-400 bg-yellow-950/30"
                    : "border-slate-800 text-slate-600 hover:border-slate-700 hover:text-slate-400"
                  }`}
              >
                {id}
              </button>
            ))}
          </div>
        </div>

        {/* Drop zone */}
        <div
          className={`
            relative flex-1 hud-panel flex flex-col items-center justify-center gap-4
            border-2 border-dashed cursor-pointer transition-all duration-200 min-h-[240px]
            ${isDragOver
              ? "border-yellow-400/60 bg-yellow-950/20 scale-[1.01]"
              : dragError
              ? "border-red-600/40 bg-red-950/10"
              : "border-slate-700/60 hover:border-slate-600/60 hover:bg-slate-900/30"
            }
          `}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPTED_EXTS}
            multiple
            className="hidden"
            onChange={handleFileChange}
          />

          {/* Icon */}
          <div className={`relative transition-colors ${isDragOver ? "text-yellow-400" : dragError ? "text-red-500" : "text-slate-700"}`}>
            {dragError ? (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1} className="w-14 h-14">
                <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0zM12 9v4M12 17h.01" />
              </svg>
            ) : (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1} className="w-14 h-14">
                <rect x="2" y="3" width="20" height="14" rx="2" />
                <path d="M8 21h8M12 17v4M9 8l3-3 3 3M12 5v7" />
              </svg>
            )}
            {isDragOver && (
              <div className="absolute inset-0 bg-yellow-400/20 blur-xl rounded-full scale-150" />
            )}
          </div>

          {/* Text */}
          {dragError ? (
            <div className="text-center">
              <p className="font-mono text-[10px] text-red-400 tracking-wider">{dragError}</p>
              <p className="font-mono text-[9px] text-slate-600 mt-1">Click to try again</p>
            </div>
          ) : isDragOver ? (
            <div className="text-center">
              <p className="font-orbitron text-sm font-bold text-yellow-400 tracking-[0.2em]">RELEASE TO QUEUE</p>
              <p className="font-mono text-[9px] text-yellow-600 mt-1">Files will be added to processing queue</p>
            </div>
          ) : (
            <div className="text-center">
              <p className="font-orbitron text-sm font-bold text-slate-500 tracking-[0.15em]">DRAG & DROP VIDEO FILES</p>
              <p className="font-mono text-[9px] text-slate-700 mt-1">or click to browse</p>
              <p className="font-mono text-[8px] text-slate-800 mt-3">MP4 · AVI · MOV · MKV &nbsp;·&nbsp; MAX {MAX_SIZE_GB}GB</p>
            </div>
          )}

          {/* Corner decorations */}
          <div className={`absolute top-2 left-2 w-4 h-4 border-t-2 border-l-2 transition-colors ${isDragOver ? "border-yellow-400/60" : "border-slate-800"}`} />
          <div className={`absolute top-2 right-2 w-4 h-4 border-t-2 border-r-2 transition-colors ${isDragOver ? "border-yellow-400/60" : "border-slate-800"}`} />
          <div className={`absolute bottom-2 left-2 w-4 h-4 border-b-2 border-l-2 transition-colors ${isDragOver ? "border-yellow-400/60" : "border-slate-800"}`} />
          <div className={`absolute bottom-2 right-2 w-4 h-4 border-b-2 border-r-2 transition-colors ${isDragOver ? "border-yellow-400/60" : "border-slate-800"}`} />
        </div>
      </div>

      {/* ── Right: Job Queue ── */}
      <div className="w-80 flex-shrink-0 flex flex-col hud-panel min-h-0">
        {/* Queue header */}
        <div className="flex items-center justify-between px-3 py-2.5 border-b border-slate-800/60 flex-shrink-0">
          <div className="flex items-center gap-2">
            <span className="font-orbitron text-[10px] font-bold text-slate-400 tracking-[0.2em]">PROCESSING QUEUE</span>
            {jobs.length > 0 && (
              <span className="w-4 h-4 rounded-full bg-yellow-900/60 border border-yellow-800/60
                font-mono text-[8px] text-yellow-400 flex items-center justify-center">
                {jobs.length}
              </span>
            )}
          </div>
          {jobs.length > 0 && (
            <button
              onClick={() => setJobs((j) => j.filter((x) => x.status !== "done"))}
              className="font-mono text-[8px] text-slate-600 hover:text-slate-400 transition-colors"
            >
              CLEAR DONE
            </button>
          )}
        </div>

        {/* Job list */}
        <div className="flex-1 overflow-y-auto p-2 space-y-1.5 min-h-0">
          {jobs.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center gap-2 py-8">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1} className="w-8 h-8 text-slate-800">
                <path d="M9 12h6M9 16h6M7 4H4a2 2 0 00-2 2v14a2 2 0 002 2h16a2 2 0 002-2V6a2 2 0 00-2-2h-3" />
                <rect x="7" y="2" width="10" height="4" rx="1" />
              </svg>
              <p className="font-mono text-[9px] text-slate-700 tracking-widest text-center">
                QUEUE EMPTY<br />Drop files to start
              </p>
            </div>
          ) : (
            jobs.map((job) => (
              <JobCard
                key={job.job_id}
                job={job}
                onRemove={() => removeJob(job.job_id)}
                onRetry={() => retryJob(job.job_id)}
              />
            ))
          )}
        </div>

        {/* Stats footer */}
        {jobs.length > 0 && (
          <div className="border-t border-slate-800/60 px-3 py-2 flex-shrink-0 grid grid-cols-3 gap-2">
            {(["queued", "processing", "done"] as JobStatus[]).map((s) => {
              const count = jobs.filter((j) => j.status === s).length;
              const style = STATUS_STYLE[s];
              return (
                <div key={s} className="text-center">
                  <div className={`font-mono text-sm font-bold ${style.text}`}>{count}</div>
                  <div className="font-mono text-[7px] text-slate-700 tracking-widest">{statusLabel(s)}</div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Job Card ────────────────────────────────────────────────

function JobCard({
  job,
  onRemove,
  onRetry,
}: {
  job: UploadJob;
  onRemove: () => void;
  onRetry: () => void;
}) {
  const style = STATUS_STYLE[job.status];
  const progress = job.progress ?? 0;

  return (
    <div className={`relative rounded-sm border p-2.5 transition-all ${style.bg} ${style.border}`}>
      {/* Top row */}
      <div className="flex items-start justify-between gap-2 mb-1.5">
        <div className="flex-1 min-w-0">
          <p className="font-mono text-[10px] text-slate-200 truncate leading-tight">{job.filename}</p>
          <div className="flex items-center gap-2 mt-0.5">
            <span className="font-mono text-[8px] text-slate-600">{formatBytes(job.size_bytes)}</span>
            <span className="font-mono text-[7px] text-slate-700">·</span>
            <span className={`font-mono text-[8px] border px-1 rounded-sm ${
              job.camera_id === "CAM-01" ? "border-cyan-900 text-cyan-500" :
              job.camera_id === "CAM-02" ? "border-pink-900 text-pink-500" :
              job.camera_id === "CAM-03" ? "border-yellow-900 text-yellow-500" :
              "border-slate-700 text-slate-500"
            }`}>
              {job.camera_id}
            </span>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1 flex-shrink-0">
          {job.status === "error" && (
            <button
              onClick={onRetry}
              title="Retry"
              className="p-1 text-yellow-600 hover:text-yellow-400 transition-colors"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-3 h-3">
                <path d="M1 4v6h6M23 20v-6h-6" /><path d="M20.49 9A9 9 0 005.64 5.64L1 10M23 14l-4.64 4.36A9 9 0 013.51 15" />
              </svg>
            </button>
          )}
          {(job.status === "done" || job.status === "error") && (
            <button
              onClick={onRemove}
              title="Remove"
              className="p-1 text-slate-700 hover:text-slate-400 transition-colors"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-3 h-3">
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>
      </div>

      {/* Status badge + progress */}
      <div className="flex items-center justify-between mb-1.5">
        <div className={`flex items-center gap-1 font-mono text-[8px] font-bold ${style.text}`}>
          {job.status === "processing" && (
            <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
          )}
          {job.status === "done" && (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} className="w-2.5 h-2.5">
              <path d="M20 6L9 17l-5-5" />
            </svg>
          )}
          {job.status === "error" && (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} className="w-2.5 h-2.5">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          )}
          {statusLabel(job.status)}
        </div>
        {job.status !== "error" && (
          <span className={`font-mono text-[8px] tabular-nums ${style.text}`}>
            {Math.round(progress)}%
          </span>
        )}
      </div>

      {/* Progress bar */}
      {job.status !== "error" && (
        <div className="h-1 bg-slate-800/60 rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-300"
            style={{
              width: `${progress}%`,
              background: style.barColor,
              boxShadow: job.status === "processing" ? `0 0 6px ${style.barColor}` : "none",
            }}
          />
        </div>
      )}

      {/* Error message */}
      {job.status === "error" && job.error && (
        <p className="font-mono text-[8px] text-red-500 mt-1 leading-relaxed">{job.error}</p>
      )}

      {/* Done: estimated detections */}
      {job.status === "done" && (
        <p className="font-mono text-[8px] text-green-600 mt-1">
          ✓ Indexed · {Math.floor(job.size_bytes / 800_000)} detections found
        </p>
      )}
    </div>
  );
}

// ─── Simulate upload + processing ─────────────────────────────

async function simulateUpload(
  jobId: string,
  file: File,
  cameraId: string,
  setJobs: React.Dispatch<React.SetStateAction<UploadJob[]>>
) {
  const update = (patch: Partial<UploadJob>) =>
    setJobs((prev) => prev.map((j) => (j.job_id === jobId ? { ...j, ...patch } : j)));

  // Phase 1: uploading (0→100 progress)
  update({ status: "processing" });

  const uploadSteps = 20;
  const uploadMs = Math.min(file.size / 200_000, 3000); // proportional, capped 3s
  const stepMs = uploadMs / uploadSteps;

  for (let i = 1; i <= uploadSteps; i++) {
    await sleep(stepMs);
    update({ progress: Math.round((i / uploadSteps) * 60) }); // 0→60 during upload
  }

  // Phase 2: backend processing (60→100)
  const procSteps = 10;
  const procMs = 2000;

  try {
    // Real API call
    const form = new FormData();
    form.append("video", file);
    form.append("camera_id", cameraId);
    await fetch("/api/input/upload-video", { method: "POST", body: form });
  } catch {
    // Backend may not be running in dev — continue simulation
  }

  for (let i = 1; i <= procSteps; i++) {
    await sleep(procMs / procSteps);
    update({ progress: 60 + Math.round((i / procSteps) * 40) }); // 60→100
  }

  update({ status: "done", progress: 100 });
}

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}