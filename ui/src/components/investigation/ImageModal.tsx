"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import Image from "next/image";
import { useInvestigation } from "./InvestigationContext";
import type { SearchResult } from "@/types";

export default function ImageModal() {
  const { state, closeImage, openTrace, setDetectionDetail } = useInvestigation();
  const { imageTarget, detectionDetail } = state;
  const overlayRef = useRef<HTMLDivElement>(null);
  const [showVideo, setShowVideo] = useState(false);

  // Auto-show video if detectionDetail has video_id
  useEffect(() => {
    if (detectionDetail?.video_id) {
      setShowVideo(true);
    }
  }, [detectionDetail]);

  // Keyboard close
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") closeImage(); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [closeImage]);

  // Backdrop click close
  const handleOverlayClick = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === overlayRef.current) closeImage();
    },
    [closeImage]
  );

  if (!imageTarget) return null;

  const handleOpenTrace = () => {
    // Close image modal and open trace modal
    closeImage();
    // Use the existing openTrace from context
    openTrace(imageTarget);
  };

  const openVideo = () => {
    // Get video info from detectionDetail
    const videoId = detectionDetail?.video_id;
    const timeOffset = detectionDetail?.video_time_offset;

    if (videoId) {
      if (showVideo) {
        // If video is already showing, open in search page
        const params = new URLSearchParams({
          video: videoId,
          time: timeOffset?.toString() || "0",
          timestamp: detectionDetail?.timestamp || imageTarget.timestamp,
          camera_id: detectionDetail?.camera_id || imageTarget.camera_id,
          clothing_class: detectionDetail?.class_name || imageTarget.clothing_class,
          color: detectionDetail?.category || imageTarget.color,
          confidence: (detectionDetail?.confidence || imageTarget.confidence)?.toString() || "0",
          play: "true" // Add play parameter
        });
        window.open(`/search?${params.toString()}`, '_blank');
      } else {
        // Show video in modal
        setShowVideo(true);
      }
    } else {
      alert('No video available for this detection');
    }
  };

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm"
      onClick={handleOverlayClick}
      style={{ animation: "fade-in 0.2s ease-out" }}
    >
      {/* ขยายความกว้าง Modal เป็น max-w-7xl เพื่อรองรับ Layout แบบมี video */}
      <div
        className="relative w-full max-w-7xl max-h-[90vh] hud-panel flex flex-col overflow-hidden bg-slate-900/90"
        style={{ animation: "slide-in-up 0.3s ease-out" }}
      >
        {/* Top accent line */}
        <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-cyan-500 to-transparent" />

        {/* ── Header ── */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800/60 flex-shrink-0">
          <div>
            {/* ปรับขนาด Header ให้ใหญ่ขึ้น */}
            <h2 className="font-orbitron text-lg font-bold text-cyan-400 tracking-[0.2em]">
              DETAIL VIEW
            </h2>
            <p className="font-mono text-sm text-slate-400 mt-1 tracking-widest">
              ID: {detectionDetail?.id || imageTarget.id} · {detectionDetail?.class_name || imageTarget.clothing_class} · {detectionDetail?.category || imageTarget.color}
            </p>
          </div>
          <button
            onClick={closeImage}
            className="p-2 rounded-sm border border-slate-700 text-slate-500 hover:border-slate-600 hover:text-slate-300 transition-colors"
          >
            {/* ขยายขนาด Icon กากบาท */}
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-6 h-6">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* ── Body (แบ่งซ้าย-กลาง-ขวา) ── */}
        <div className="flex flex-col lg:flex-row flex-1 overflow-hidden min-h-0">
          
          {/* ซ้าย: พื้นที่แสดงรูปภาพ */}
          <div className={`relative flex-1 min-h-[400px] md:min-h-[500px] transition-all duration-300 ${showVideo ? 'lg:w-1/2' : ''}`}>
            {(detectionDetail?.image_url || imageTarget.thumbnail_url) && (detectionDetail?.image_url || imageTarget.thumbnail_url)?.trim() !== "" ? (
              <Image
                src={detectionDetail?.image_url || imageTarget.thumbnail_url}
                alt="Detection"
                fill
                className="object-contain p-2"
                unoptimized
              />
            ) : (
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="text-center">
                  <div className="text-slate-500 text-sm">No image available</div>
                </div>
              </div>
            )}
            {/* Neon frame */}
            <div className="absolute inset-0 pointer-events-none border border-cyan-500/20" />
            <div className="absolute top-2 left-2 w-4 h-4 border-t-2 border-l-2 border-cyan-400/60" />
            <div className="absolute bottom-2 right-2 w-4 h-4 border-b-2 border-r-2 border-cyan-400/60" />
            {/* Scanlines */}
            <div className="absolute inset-0 pointer-events-none"
              style={{ background: "repeating-linear-gradient(0deg,transparent,transparent 3px,rgba(0,0,0,0.08) 3px,rgba(0,0,0,0.08) 4px)" }} />
          </div>

          {/* กลาง: Video Player (แสดงเมื่อกดปุ่ม VIDEO) */}
          {showVideo && (
            <div className="relative lg:w-1/2 min-h-[400px] md:min-h-[500px] bg-black">
              <video
                controls
                className="w-full h-full object-contain"
                src={`/api/video/videos/${detectionDetail?.video_id}/stream`}
                ref={(videoElement) => {
                  if (videoElement && detectionDetail?.video_time_offset) {
                    // Seek to time offset when video loads
                    videoElement.addEventListener('loadedmetadata', () => {
                      videoElement.currentTime = parseFloat(detectionDetail.video_time_offset.toString());
                    });
                  }
                }}
              >
                Your browser does not support the video tag.
              </video>
              {/* Video frame */}
              <div className="absolute inset-0 pointer-events-none border border-purple-500/20" />
              <div className="absolute top-2 right-2 w-4 h-4 border-t-2 border-r-2 border-purple-400/60" />
              <div className="absolute bottom-2 left-2 w-4 h-4 border-b-2 border-l-2 border-purple-400/60" />
            </div>
          )}

          {/* ขวา: แถบรายละเอียดและปุ่ม */}
          <div className={`w-full md:w-80 border-t md:border-t-0 md:border-l border-slate-800/60 bg-slate-950/50 flex flex-col flex-shrink-0 overflow-y-auto transition-all duration-300 ${showVideo ? 'lg:w-80' : ''}`}>
            {/* ข้อมูลรายละเอียด */}
            <div className="p-6 flex-1 flex flex-col gap-6">
              <div>
                <span className="font-mono text-sm text-slate-500 uppercase tracking-wider block mb-1">CAMERA</span>
                <p className="font-mono text-cyan-400 font-bold text-lg">{detectionDetail?.camera_id || imageTarget.camera_id}</p>
              </div>
              <div>
                <span className="font-mono text-sm text-slate-500 uppercase tracking-wider block mb-1">TIME</span>
                <p className="font-mono text-slate-200 text-lg">
                  {new Date(detectionDetail?.video_time_offset || imageTarget.timestamp).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                </p>
              </div>
              <div>
                <span className="font-mono text-sm text-slate-500 uppercase tracking-wider block mb-1">DATE</span>
                <p className="font-mono text-slate-200 text-lg">
                  {new Date(detectionDetail?.video_time_offset || imageTarget.timestamp).toLocaleDateString("en-GB", { day: "2-digit", month: "short" }).toUpperCase()}
                </p>
              </div>
              <div>
                <span className="font-mono text-sm text-slate-500 uppercase tracking-wider block mb-1">CONFIDENCE</span>
                <p className="font-mono text-green-400 font-bold text-lg">{Math.round((detectionDetail?.confidence || imageTarget.confidence) * 100)}%</p>
              </div>

              {detectionDetail?.video_id && (
                <div className="mt-2 pt-6 border-t border-slate-800/60 flex flex-col gap-6">
                  <div>
                    <span className="font-mono text-sm text-slate-500 uppercase tracking-wider block mb-1">VIDEO ID</span>
                    <p className="font-mono text-purple-400 font-bold text-base break-all">{detectionDetail.video_id}</p>
                  </div>
                  <div>
                    <span className="font-mono text-sm text-slate-500 uppercase tracking-wider block mb-1">TIME OFFSET</span>
                    <p className="font-mono text-purple-400 font-bold text-lg">{detectionDetail.video_time_offset}s</p>
                  </div>
                </div>
              )}
            </div>

            {/* ปุ่มกด (ย้ายมาไว้ล่างสุดของ Sidebar) */}
            <div className="p-4 border-t border-slate-800/60 flex flex-col gap-3">
              <button
                onClick={handleOpenTrace}
                className="w-full py-3 bg-cyan-950/60 border border-cyan-700/60 rounded-sm
                  font-mono text-sm font-bold tracking-widest text-cyan-400 hover:bg-cyan-900/60 transition-colors"
              >
                TRACE
              </button>
              <button
                onClick={openVideo}
                className="w-full py-3 bg-purple-950/60 border border-purple-700/60 rounded-sm
                  font-mono text-sm font-bold tracking-widest text-purple-400 hover:bg-purple-900/60 transition-colors"
              >
                {showVideo ? 'OPEN IN SEARCH' : 'VIDEO'}
              </button>
            </div>
          </div>
          
        </div>
      </div>
    </div>
  );
}