"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import Image from "next/image";
import { useInvestigation } from "./InvestigationContext";
import type { SearchResult } from "@/types";

export default function ImageModal() {
  const { state, closeImage, openTrace, setDetectionDetail } = useInvestigation();
  const { imageTarget, detectionDetail } = state;
  const overlayRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const [showVideo, setShowVideo] = useState(false);
  const [showColorInfo, setShowColorInfo] = useState(false);
  
  // สร้าง State สำหรับเก็บค่า Time Offset ที่ผู้ใช้สามารถปรับเพิ่ม/ลดได้
  const [targetOffset, setTargetOffset] = useState<number>(0);

  // ตั้งค่า targetOffset เริ่มต้นให้เท่ากับค่าจาก API 
  useEffect(() => {
    if (detectionDetail?.video_time_offset !== undefined) {
      setTargetOffset(Number(detectionDetail.video_time_offset));
      setShowVideo(true);
    }
    // Debug: แสดงค่า detectionDetail ที่ได้รับ
    console.log('DetectionDetail:', detectionDetail);
    console.log('Video ID:', detectionDetail?.video_id);
  }, [detectionDetail]);

  // Keyboard close
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") closeImage(); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [closeImage]);

  const handleOverlayClick = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === overlayRef.current) closeImage();
    },
    [closeImage]
  );

  if (!imageTarget) return null;

  const handleOpenTrace = () => {
    closeImage();
    openTrace(imageTarget);
  };

  const openVideo = () => {
    const videoId = detectionDetail?.video_id;

    if (videoId) {
      if (showVideo) {
        const params = new URLSearchParams({
          video: videoId,
          time: targetOffset.toString(), // ใช้ targetOffset ที่ถูกปรับแล้วแทนค่าเดิม
          timestamp: detectionDetail?.timestamp || imageTarget.timestamp,
          camera_id: detectionDetail?.camera_id || imageTarget.camera_id,
          clothing_class: detectionDetail?.class_name || imageTarget.clothing_class,
          color: detectionDetail?.category || imageTarget.color,
          confidence: (detectionDetail?.confidence || imageTarget.confidence)?.toString() || "0",
          play: "true"
        });
        window.open(`/search?${params.toString()}`, '_blank');
      } else {
        setShowVideo(true);
      }
    } else {
      alert('No video available for this detection');
    }
  };

  // ----- ฟังก์ชันสำหรับจัดการ Time Offset -----
  
// 1. กระโดดไปที่ targetOffset ปัจจุบัน แล้วสั่ง Play
  const jumpToTargetOffset = () => {
    if (videoRef.current) {
      videoRef.current.currentTime = targetOffset;
      
      // เก็บค่า Promise ของการเล่นวิดีโอ
      const playPromise = videoRef.current.play();

      // ตรวจสอบว่าเบราว์เซอร์รองรับ Promise จาก play() ไหม (เบราว์เซอร์ยุคใหม่รองรับหมดแล้ว)
      if (playPromise !== undefined) {
        playPromise.catch((error) => {
          if (error.name === 'AbortError') {
            // ถ้าเป็น AbortError (กดหยุดก่อนเล่น) ให้เงียบไว้ หรือแค่ Log ขำๆ พอ
            console.log("Play interrupted (e.g., user paused or closed the modal too quickly)");
          } else {
            // ถ้าเป็น Error อื่นๆ ค่อยแสดงออกมา
            console.error("Video play error:", error);
          }
        });
      }
    }
  };

  // 2. ปรับเพิ่ม/ลด ตัวเลข targetOffset (ไม่ให้ติดลบ)
  const adjustOffset = (seconds: number) => {
    setTargetOffset(prev => Math.max(0, prev + seconds));
  };

  // 3. รีเซ็ตกลับไปเป็นค่าดั้งเดิมจาก API
  const resetOffset = () => {
    if (detectionDetail?.video_time_offset !== undefined) {
      setTargetOffset(Number(detectionDetail.video_time_offset));
    }
  };

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm"
      onClick={handleOverlayClick}
      style={{ animation: "fade-in 0.2s ease-out" }}
    >
      <div
        className="relative w-full max-w-7xl max-h-[90vh] hud-panel flex flex-col overflow-hidden bg-slate-900/90"
        style={{ animation: "slide-in-up 0.3s ease-out" }}
      >
        <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-cyan-500 to-transparent" />

{/* ── Header ── */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800/60 flex-shrink-0">
          <div>
            <h2 className="font-orbitron text-lg font-bold text-cyan-400 tracking-[0.2em]">
              DETAIL VIEW
            </h2>
            
            {/* ซ่อน ID และทำ 2 ค่าที่เหลือให้เป็น Tag เด่นๆ */}
            <div className="flex items-center gap-3 mt-2.5">
              <span className="px-3 py-1 bg-cyan-950/60 border border-cyan-700/50 rounded-sm font-mono text-sm font-bold text-cyan-300 uppercase tracking-widest shadow-[0_0_10px_rgba(6,182,212,0.15)]">
                {detectionDetail?.class_name || imageTarget.clothing_class}
              </span>
              <span className="px-3 py-1 bg-purple-950/60 border border-purple-700/50 rounded-sm font-mono text-sm font-bold text-purple-300 uppercase tracking-widest shadow-[0_0_10px_rgba(168,85,247,0.15)]">
                {detectionDetail?.category || imageTarget.color}
              </span>
            </div>
            
          </div>
          <button
            onClick={closeImage}
            className="p-2 rounded-sm border border-slate-700 text-slate-500 hover:border-slate-600 hover:text-slate-300 transition-colors"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-6 h-6">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex flex-col lg:flex-row flex-1 overflow-hidden min-h-0">
          
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
            <div className="absolute inset-0 pointer-events-none border border-cyan-500/20" />
            <div className="absolute top-2 left-2 w-4 h-4 border-t-2 border-l-2 border-cyan-400/60" />
            <div className="absolute bottom-2 right-2 w-4 h-4 border-b-2 border-r-2 border-cyan-400/60" />
            <div className="absolute inset-0 pointer-events-none"
              style={{ background: "repeating-linear-gradient(0deg,transparent,transparent 3px,rgba(0,0,0,0.08) 3px,rgba(0,0,0,0.08) 4px)" }} />
          </div>

          {showVideo && detectionDetail?.video_id && (
            <div className="relative lg:w-1/2 min-h-[400px] md:min-h-[500px] bg-black">
              <video
                ref={videoRef}
                controls
                className="w-full h-full object-contain"
                src={`/api/video/videos/${detectionDetail.video_id}/stream`}
                onLoadedMetadata={() => {
                  // ตอนโหลดวิดีโอครั้งแรก ให้กระโดดไปที่ Original Offset เลย
                  if (videoRef.current && detectionDetail?.video_time_offset !== undefined) {
                    videoRef.current.currentTime = Number(detectionDetail.video_time_offset);
                  }
                }}
              >
                Your browser does not support the video tag.
              </video>
              <div className="absolute inset-0 pointer-events-none border border-purple-500/20" />
              <div className="absolute top-2 right-2 w-4 h-4 border-t-2 border-r-2 border-purple-400/60" />
              <div className="absolute bottom-2 left-2 w-4 h-4 border-b-2 border-l-2 border-purple-400/60" />
            </div>
          )}

          {showVideo && !detectionDetail?.video_id && (
            <div className="relative lg:w-1/2 min-h-[400px] md:min-h-[500px] bg-black flex items-center justify-center">
              <div className="text-center text-slate-400">
                <p className="text-lg font-mono">NO VIDEO AVAILABLE</p>
                <p className="text-sm mt-2">This detection has no associated video</p>
              </div>
            </div>
          )}

          <div className={`w-full md:w-80 border-t md:border-t-0 md:border-l border-slate-800/60 bg-slate-950/50 flex flex-col flex-shrink-0 overflow-y-auto transition-all duration-300 ${showVideo ? 'lg:w-80' : ''}`}>
            <div className="p-6 flex-1 flex flex-col gap-6">
              <div>
                <span className="font-mono text-sm text-slate-500 uppercase tracking-wider block mb-1">CAMERA</span>
                <p className="font-mono text-cyan-400 font-bold text-lg">{detectionDetail?.camera_id || imageTarget.camera_id}</p>
              </div>
              <div>
                <span className="font-mono text-sm text-slate-500 uppercase tracking-wider block mb-1">TIME</span>
                <p className="font-mono text-slate-200 text-lg">
                  {new Date(detectionDetail?.timestamp || imageTarget.timestamp).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                </p>
              </div>
              <div>
                <span className="font-mono text-sm text-slate-500 uppercase tracking-wider block mb-1">DATE</span>
                <p className="font-mono text-slate-200 text-lg">
                  {new Date(detectionDetail?.timestamp || imageTarget.timestamp).toLocaleDateString("en-GB", { day: "2-digit", month: "short" }).toUpperCase()}
                </p>
              </div>
              <div>
                <span className="font-mono text-sm text-slate-500 uppercase tracking-wider block mb-1">CONFIDENCE</span>
                <p className="font-mono text-green-400 font-bold text-lg">{Math.round((detectionDetail?.confidence || imageTarget.confidence) * 100)}%</p>
              </div>

              {detectionDetail?.video_id && (
                <div className="mt-2 pt-6 border-t border-slate-800/60 flex flex-col gap-6 ">
                  <div>
                    <span className="font-mono text-sm text-slate-500 uppercase tracking-wider block mb-1">VIDEO ID</span>
                    <p className="font-mono text-purple-400 font-bold text-base break-all">{detectionDetail.video_id}</p>
                  </div>
                  <div>
                    <span className="font-mono text-sm text-slate-500 uppercase tracking-wider block mb-1">TARGET OFFSET</span>
                    <div className="flex flex-col gap-3 mt-1">
                      
                      {/* บรรทัดแรก: แสดงค่า targetOffset เดี่ยวๆ */}
                      <p className="font-mono text-purple-400 font-bold text-xl">
                        {targetOffset.toFixed(2)}s
                      </p>
                      
                      {showVideo && (
                        <div className="flex flex-col gap-2 mt-1">
                          {/* บรรทัดที่สอง: ปุ่มปรับ Offset (+, -, Reset) */}
                          <div className="flex items-center gap-2">
                            <button
                              onClick={() => adjustOffset(-1)}
                              className="cursor-pointer px-3 py-1.5 bg-slate-800/80 text-slate-300 font-mono text-sm font-bold rounded hover:bg-slate-700 hover:text-white transition-colors border border-slate-700"
                              title="Decrease target offset by 1s"
                            >
                              -1s
                            </button>
                            
                            <button
                              onClick={resetOffset}
                              className="cursor-pointer flex-1 py-1.5 bg-purple-900/40 text-purple-400 font-mono text-sm font-bold tracking-widest rounded hover:bg-purple-800/60 hover:text-purple-300 transition-colors border border-purple-700/50 flex justify-center items-center gap-1.5"
                              title="Reset to original offset"
                            >
                              <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4">
                                <path d="M12 5V1L7 6l5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z"/>
                              </svg>
                              RESET
                            </button>

                            <button
                              onClick={() => adjustOffset(1)}
                              className="cursor-pointer px-3 py-1.5 bg-slate-800/80 text-slate-300 font-mono text-sm font-bold rounded hover:bg-slate-700 hover:text-white transition-colors border border-slate-700"
                              title="Increase target offset by 1s"
                            >
                              +1s
                            </button>
                          </div>

                          {/* บรรทัดที่สาม: ปุ่ม Play กระโดดไปที่เวลา (w-full) */}
                          <button
                            onClick={jumpToTargetOffset}
                            className="cursor-pointer w-full py-2 bg-purple-600/20 text-purple-400 font-mono text-sm font-bold tracking-widest rounded hover:bg-purple-600/40 hover:text-purple-200 transition-colors border border-purple-500/50 flex justify-center items-center gap-2 mt-1"
                            title="Jump to target offset and play"
                          >
                            <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4">
                              <path d="M8 5v14l11-7z" />
                            </svg>
                            PLAY
                          </button>
                        </div>
                      )}

                    </div>
                  </div>
                </div>
              )}
            </div>

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
              <button
                onClick={() => setShowColorInfo(true)}
                className="w-full py-3 bg-slate-800/70 border border-cyan-600/80 rounded-sm
                  font-mono text-sm font-bold tracking-widest text-cyan-300 hover:bg-cyan-900/30 transition-colors"
              >
                COLOR DETAILS
              </button>
            </div>
          </div>
          
        </div>
      </div>

      {showColorInfo && (
        <div className="fixed inset-0 z-60 flex items-center justify-center p-6 bg-slate-950/80 backdrop-blur-sm">
          <div className="w-full max-w-md bg-slate-900 border border-cyan-700/60 rounded-md p-4">
            <div className="flex items-center justify-between mb-3">
              <div>
                <h3 className="font-orbitron text-sm text-cyan-300 tracking-widest">COLOR INFORMATION</h3>
                <p className="font-mono text-[10px] text-slate-500">Left object color data from detection.</p>
              </div>
              <button
                onClick={() => setShowColorInfo(false)}
                className="text-slate-400 hover:text-white"
              >✕</button>
            </div>

            <div className="space-y-2">
              <div className="font-mono text-[10px] text-slate-400">Detected</div>
              <div className="grid grid-cols-2 gap-2">
                <div className="p-2 bg-slate-800/50 border border-slate-700 rounded-sm">
                  <div className="text-[11px] text-slate-500">Class</div>
                  <div className="font-mono text-sm text-cyan-300 font-bold">{detectionDetail?.class_name || imageTarget.clothing_class || 'Unknown'}</div>
                </div>
                <div className="p-2 bg-slate-800/50 border border-slate-700 rounded-sm">
                  <div className="text-[11px] text-slate-500">Color</div>
                  <div className="font-mono text-sm text-purple-300 font-bold">{detectionDetail?.category || imageTarget.color || 'Unknown'}</div>
                </div>
              </div>

              <div className="pt-2 border-t border-slate-800">
                <div className="font-mono text-[9px] text-slate-500 uppercase tracking-widest mb-1">Color Profile</div>
                {detectionDetail?.color_profile ? (
                  <div className="space-y-1">
                    {Object.entries(detectionDetail.color_profile as Record<string, number>)
                      .sort((a, b) => b[1] - a[1])
                      .map(([color, value]) => (
                        <div key={color} className="flex justify-between">
                          <span className="font-mono text-[10px] uppercase text-slate-300">{color}</span>
                          <span className="font-mono text-[10px] text-cyan-300">{(value as number).toFixed(1)}%</span>
                        </div>
                      ))}
                  </div>
                ) : (
                  <div className="font-mono text-[10px] text-slate-500">No color profile data available for this target.</div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}