"use client";

import { useEffect, useRef, useState, useCallback } from "react";

// ─── Types ────────────────────────────────────────────────────

interface BoundingBox {
  id: string;
  x: number;      // 0–1 (relative)
  y: number;
  w: number;
  h: number;
  label: string;  // "Red Shirt"
  color: "green" | "red" | "yellow";
  confidence: number;
}

interface CameraOption {
  id: string;
  name: string;
  location: string;
  streamUrl: string;
  status: "online" | "offline";
}

// ─── Mock data ────────────────────────────────────────────────

const MOCK_CAMERAS: CameraOption[] = [
  { id: "CAM-01", name: "Main Entrance", location: "Gate A", streamUrl: "", status: "online" },
  { id: "CAM-02", name: "Corridor B",   location: "Floor 2", streamUrl: "", status: "online" },
  { id: "CAM-03", name: "Parking Lot",  location: "Zone C",  streamUrl: "", status: "online" },
  { id: "CAM-04", name: "Exit Gate",    location: "Gate D",  streamUrl: "", status: "offline" },
];

const MOCK_BOXES: BoundingBox[] = [
  { id: "p1", x: 0.12, y: 0.2,  w: 0.14, h: 0.55, label: "Red Shirt",    color: "green", confidence: 0.94 },
  { id: "p2", x: 0.45, y: 0.25, w: 0.12, h: 0.50, label: "Black Hoodie", color: "green", confidence: 0.88 },
  { id: "p3", x: 0.72, y: 0.18, w: 0.13, h: 0.58, label: "Blue Jeans",   color: "red",   confidence: 0.71 },
];

// ─── Component ────────────────────────────────────────────────

export default function LiveVideoCanvas() {
  const [selectedCamera, setSelectedCamera] = useState<CameraOption>(MOCK_CAMERAS[0]);
  const [showCameraList, setShowCameraList] = useState(false);
  const [hoveredBox, setHoveredBox] = useState<BoundingBox | null>(null);
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });
  const [boxes, setBoxes] = useState<BoundingBox[]>(MOCK_BOXES);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [frameCount, setFrameCount] = useState(0);
  const [fps, setFps] = useState(0);

  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const videoRef = useRef<HTMLImageElement>(null);
  const fpsIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const frameRef = useRef(0);

  // Simulate frame counter + FPS
  useEffect(() => {
    fpsIntervalRef.current = setInterval(() => {
      setFps(frameRef.current);
      frameRef.current = 0;
    }, 1000);

    const frameTimer = setInterval(() => {
      frameRef.current += 1;
      setFrameCount((c) => c + 1);
    }, 33); // ~30fps

    return () => {
      if (fpsIntervalRef.current) clearInterval(fpsIntervalRef.current);
      clearInterval(frameTimer);
    };
  }, []);

  // Animate bounding boxes slightly (jitter) for realism
  useEffect(() => {
    const jitter = setInterval(() => {
      setBoxes((prev) =>
        prev.map((b) => ({
          ...b,
          x: b.x + (Math.random() - 0.5) * 0.002,
          y: b.y + (Math.random() - 0.5) * 0.001,
        }))
      );
    }, 100);
    return () => clearInterval(jitter);
  }, []);

  // Draw bounding boxes on canvas overlay
  const drawBoxes = useCallback(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    const { width, height } = container.getBoundingClientRect();
    canvas.width = width;
    canvas.height = height;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, width, height);

    boxes.forEach((box) => {
      const x = box.x * width;
      const y = box.y * height;
      const w = box.w * width;
      const h = box.h * height;

      const color = box.color === "green"
        ? "#39ff14"
        : box.color === "red"
        ? "#ff3b3b"
        : "#ffd700";

      const isHovered = hoveredBox?.id === box.id;

      // Outer glow
      ctx.shadowColor = color;
      ctx.shadowBlur = isHovered ? 16 : 8;

      // Box
      ctx.strokeStyle = color;
      ctx.lineWidth = isHovered ? 2 : 1.5;
      ctx.setLineDash([]);
      ctx.strokeRect(x, y, w, h);

      // Corner brackets
      const cs = 10;
      ctx.lineWidth = 2.5;
      ctx.shadowBlur = 4;
      // TL
      ctx.beginPath(); ctx.moveTo(x, y + cs); ctx.lineTo(x, y); ctx.lineTo(x + cs, y); ctx.stroke();
      // TR
      ctx.beginPath(); ctx.moveTo(x + w - cs, y); ctx.lineTo(x + w, y); ctx.lineTo(x + w, y + cs); ctx.stroke();
      // BL
      ctx.beginPath(); ctx.moveTo(x, y + h - cs); ctx.lineTo(x, y + h); ctx.lineTo(x + cs, y + h); ctx.stroke();
      // BR
      ctx.beginPath(); ctx.moveTo(x + w - cs, y + h); ctx.lineTo(x + w, y + h); ctx.lineTo(x + w, y + h - cs); ctx.stroke();

      ctx.shadowBlur = 0;

      // Label tag (top-left of box)
      const tagPad = 4;
      const tagH = 16;
      const tag = `${box.label} ${Math.round(box.confidence * 100)}%`;
      ctx.font = "bold 10px 'Share Tech Mono', monospace";
      const tagW = ctx.measureText(tag).width + tagPad * 2;

      ctx.fillStyle = color + "33";
      ctx.fillRect(x, y - tagH, tagW, tagH);
      ctx.strokeStyle = color;
      ctx.lineWidth = 1;
      ctx.strokeRect(x, y - tagH, tagW, tagH);

      ctx.fillStyle = color;
      ctx.shadowColor = color;
      ctx.shadowBlur = 4;
      ctx.fillText(tag, x + tagPad, y - tagH + 11);
      ctx.shadowBlur = 0;

      // Scan line inside box (animated using frameCount)
      const scanY = y + ((frameCount * 2) % h);
      const grad = ctx.createLinearGradient(x, scanY - 6, x, scanY + 6);
      grad.addColorStop(0, "transparent");
      grad.addColorStop(0.5, color + "40");
      grad.addColorStop(1, "transparent");
      ctx.fillStyle = grad;
      ctx.fillRect(x + 1, scanY - 6, w - 2, 12);
    });
  }, [boxes, hoveredBox, frameCount]);

  useEffect(() => {
    drawBoxes();
  }, [drawBoxes]);

  // Handle hover detection on canvas
  const handleMouseMove = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      const mx = (e.clientX - rect.left) / rect.width;
      const my = (e.clientY - rect.top) / rect.height;

      setMousePos({ x: e.clientX - rect.left, y: e.clientY - rect.top });

      const hit = boxes.find(
        (b) => mx >= b.x && mx <= b.x + b.w && my >= b.y && my <= b.y + b.h
      );
      setHoveredBox(hit ?? null);
    },
    [boxes]
  );

  const handleMouseLeave = () => setHoveredBox(null);

  return (
    <div className="hud-panel flex flex-col min-h-0 overflow-hidden">
      {/* ── Top bar ── */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-cyan-900/30 flex-shrink-0">
        {/* Camera selector */}
        <div className="relative">
          <button
            onClick={() => setShowCameraList((s) => !s)}
            className="flex items-center gap-2 group"
          >
            <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse flex-shrink-0" />
            <span className="font-orbitron text-[10px] text-cyan-400 tracking-widest group-hover:text-cyan-300 transition-colors">
              {selectedCamera.name}
            </span>
            <span className="font-mono text-[8px] text-slate-600 ml-1">
              {selectedCamera.id}
            </span>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-3 h-3 text-slate-600">
              <path d="M6 9l6 6 6-6" />
            </svg>
          </button>

          {/* Dropdown */}
          {showCameraList && (
            <div className="absolute top-full left-0 mt-1 z-50 w-52 glass border border-cyan-900/50 rounded-sm shadow-xl">
              {MOCK_CAMERAS.map((cam) => (
                <button
                  key={cam.id}
                  onClick={() => { setSelectedCamera(cam); setShowCameraList(false); }}
                  className="w-full flex items-center gap-2 px-3 py-2 hover:bg-cyan-950/40 transition-colors text-left"
                >
                  <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${cam.status === "online" ? "bg-green-500" : "bg-red-500"}`} />
                  <div>
                    <div className="font-mono text-[10px] text-slate-300">{cam.name}</div>
                    <div className="font-mono text-[8px] text-slate-600">{cam.id} · {cam.location}</div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Right: FPS + Controls */}
        <div className="flex items-center gap-3">
          <span className="font-mono text-[9px] text-slate-600">
            FPS <span className="text-cyan-600">{fps}</span>
          </span>
          <span className="font-mono text-[9px] text-slate-600">
            DET <span className="text-green-500">{boxes.length}</span>
          </span>
          <button
            onClick={() => setIsFullscreen((s) => !s)}
            className="p-1 hover:text-cyan-400 text-slate-600 transition-colors"
            title="Fullscreen"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-4 h-4">
              {isFullscreen
                ? <path d="M8 3v3a2 2 0 01-2 2H3m18 0h-3a2 2 0 01-2-2V3m0 18v-3a2 2 0 012-2h3M3 16h3a2 2 0 012 2v3" />
                : <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
              }
            </svg>
          </button>
        </div>
      </div>

      {/* ── Video area ── */}
      <div
        ref={containerRef}
        className="relative flex-1 bg-slate-950 overflow-hidden cursor-crosshair min-h-0"
        style={{ minHeight: 0 }}
      >
        {selectedCamera.status === "offline" ? (
          /* Offline state */
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3">
            <div className="w-12 h-12 border border-red-900/60 rounded-full flex items-center justify-center">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-6 h-6 text-red-700">
                <path d="M18.364 5.636a9 9 0 11-12.728 0M12 3v9" />
              </svg>
            </div>
            <p className="font-mono text-[10px] text-red-700 tracking-widest">SIGNAL LOST</p>
            <p className="font-mono text-[9px] text-slate-700">{selectedCamera.id} · {selectedCamera.location}</p>
          </div>
        ) : (
          <>
            {/* Simulated video feed via CSS noise + gradient */}
            <div className="absolute inset-0">
              {/* Static "video" background - in production replace with <img> MJPEG or <video> */}
              <div
                className="w-full h-full animate-flicker"
                style={{
                  background: `
                    radial-gradient(ellipse at 30% 40%, rgba(0,30,15,0.9) 0%, transparent 60%),
                    radial-gradient(ellipse at 70% 60%, rgba(5,10,30,0.9) 0%, transparent 60%),
                    linear-gradient(160deg, #050d18 0%, #0a1520 50%, #060e14 100%)
                  `,
                }}
              />

              {/* Simulated person silhouettes */}
              {boxes.map((box) => (
                <div
                  key={box.id}
                  className="absolute opacity-30"
                  style={{
                    left: `${box.x * 100}%`,
                    top: `${box.y * 100}%`,
                    width: `${box.w * 100}%`,
                    height: `${box.h * 100}%`,
                    background: `linear-gradient(180deg, rgba(255,255,255,0.08) 0%, rgba(255,255,255,0.04) 100%)`,
                    borderRadius: "2px",
                  }}
                />
              ))}

              {/* Scanline overlay */}
              <div
                className="absolute inset-0 pointer-events-none"
                style={{
                  background: "repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,0.08) 2px,rgba(0,0,0,0.08) 4px)",
                }}
              />

              {/* Vignette */}
              <div
                className="absolute inset-0 pointer-events-none"
                style={{
                  background: "radial-gradient(ellipse at center, transparent 50%, rgba(0,0,0,0.7) 100%)",
                }}
              />
            </div>

            {/* Canvas overlay for bounding boxes */}
            <canvas
              ref={canvasRef}
              className="absolute inset-0 w-full h-full"
              onMouseMove={handleMouseMove}
              onMouseLeave={handleMouseLeave}
            />

            {/* Hover tooltip */}
            {hoveredBox && (
              <div
                className="absolute z-10 pointer-events-none glass border border-cyan-500/40 px-2.5 py-2 rounded-sm shadow-neon-cyan"
                style={{
                  left: mousePos.x + 12,
                  top: mousePos.y + 12,
                  transform: mousePos.x > (containerRef.current?.offsetWidth ?? 0) * 0.7 ? "translateX(-110%)" : undefined,
                }}
              >
                <div className="font-orbitron text-[9px] text-cyan-400 tracking-wider mb-1">DETECTED</div>
                <div className="font-mono text-[10px] text-slate-200">{hoveredBox.label}</div>
                <div className="font-mono text-[9px] text-slate-500 mt-0.5">
                  CONF: <span className="text-cyan-400">{Math.round(hoveredBox.confidence * 100)}%</span>
                </div>
                <div className="font-mono text-[9px] text-slate-500">ID: {hoveredBox.id}</div>
              </div>
            )}

            {/* Corner HUD decorations */}
            <div className="absolute top-2 left-2 pointer-events-none">
              <div className="font-mono text-[8px] text-cyan-900 tracking-wider">
                {selectedCamera.id} · {selectedCamera.location}
              </div>
            </div>

            {/* REC indicator */}
            <div className="absolute top-2 right-2 flex items-center gap-1.5 pointer-events-none">
              <div className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
              <span className="font-mono text-[8px] text-red-500 tracking-widest">REC</span>
            </div>

            {/* Bottom timestamp */}
            <div className="absolute bottom-2 left-2 font-mono text-[8px] text-slate-700 pointer-events-none">
              <LiveTimestamp />
            </div>

            {/* Crosshair center */}
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-10">
              <div className="relative w-8 h-8">
                <div className="absolute left-1/2 top-0 bottom-0 w-px bg-cyan-400 -translate-x-1/2" />
                <div className="absolute top-1/2 left-0 right-0 h-px bg-cyan-400 -translate-y-1/2" />
                <div className="absolute inset-1 border border-cyan-400 rounded-full" />
              </div>
            </div>
          </>
        )}
      </div>

      {/* ── Bottom bar: camera strip ── */}
      <div className="flex items-center gap-2 px-3 py-2 border-t border-cyan-900/20 flex-shrink-0 overflow-x-auto">
        {MOCK_CAMERAS.map((cam) => (
          <button
            key={cam.id}
            onClick={() => setSelectedCamera(cam)}
            className={`
              flex-shrink-0 flex items-center gap-1.5 px-2 py-1 rounded-sm border transition-all
              ${selectedCamera.id === cam.id
                ? "border-cyan-500/60 bg-cyan-950/40 text-cyan-400"
                : "border-slate-800 bg-transparent text-slate-600 hover:border-slate-700 hover:text-slate-400"
              }
            `}
          >
            <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${cam.status === "online" ? "bg-green-500" : "bg-red-600"}`} />
            <span className="font-mono text-[9px] tracking-wider">{cam.id}</span>
          </button>
        ))}
        <div className="flex-1" />
        <span className="font-mono text-[8px] text-slate-700 flex-shrink-0 tracking-widest">
          {MOCK_CAMERAS.filter(c => c.status === "online").length}/{MOCK_CAMERAS.length} ONLINE
        </span>
      </div>
    </div>
  );
}

function LiveTimestamp() {
  const [ts, setTs] = useState("");
  useEffect(() => {
    const update = () => setTs(new Date().toLocaleTimeString("en-GB", { hour12: false }));
    update();
    const t = setInterval(update, 1000);
    return () => clearInterval(t);
  }, []);
  return <span>{ts}</span>;
}