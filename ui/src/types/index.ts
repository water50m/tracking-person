// ============================================================
// NEXUS-EYE · Shared TypeScript Types
// ============================================================

// ─── Search & Detection ─────────────────────────────────────

export type ClothingClass =
  | "short sleeve top"
  | "long sleeve top"
  | "short sleeve outwear"
  | "long sleeve outwear"
  | "vest"
  | "sling"
  | "shorts"
  | "trousers"
  | "skirt"
  | "short sleeve dress"
  | "long sleeve dress"
  | "vest dress"
  | "sling dress"
  | "Unknown";

export type ClothingColor =
  | "Red"
  | "Blue"
  | "Black"
  | "White"
  | "Yellow"
  | "Green"
  | "Orange"
  | "Purple"
  | "Pink"
  | "Brown"
  | "Gray"
  | "Navy"
  | "Unknown";

export interface AttributeDetectionResult {
  class: ClothingClass;
  color: ClothingColor;
  confidence: number;
  secondary_color?: ClothingColor | null;
  attributes?: string[];
}

export interface SearchFilters {
  clothing: ClothingClass[];
  colors: ClothingColor[];
  logic: "OR" | "AND";
  threshold: number;
  camera_id?: string;
  start_time?: string;
  end_time?: string;
}

export interface SearchResult {
  id: string;
  thumbnail_url: string;
  camera_id: string;
  camera_name?: string;
  timestamp: string;
  clothing_class: ClothingClass;
  color: ClothingColor;
  confidence: number;
}

export interface SearchResultsResponse {
  results: SearchResult[];
  total: number;
  page: number;
  has_more: boolean;
}

// ─── Trace / Journey ─────────────────────────────────────────

export interface TraceEvent {
  id: string;
  camera_id: string;
  camera_name: string;
  timestamp: string;
  thumbnail_url: string | null;
  confidence: number;
  bounding_box?: {
    x: number;
    y: number;
    w: number;
    h: number;
  } | null;
}

export interface TraceResponse {
  person_id: string;
  thumbnail_url: string | null;
  detections: TraceEvent[];
  cameras: string[];
  attributes: Partial<Record<string, string>>;
}

// ─── Live Events (SSE) ───────────────────────────────────────

export interface LiveDetectionEvent {
  type: "detection";
  payload: {
    id: string;
    camera_id: string;
    timestamp: string;
    clothing: string;
    confidence: number;
    thumbnail_url: string;
  };
}

export interface LiveStatsEvent {
  type: "stats_update";
  payload: {
    total_today: number;
    active_cameras: number;
    detections_per_hour: number;
  };
}

export interface HeartbeatEvent {
  type: "heartbeat";
  ts: number;
}

export type SSEEvent = LiveDetectionEvent | LiveStatsEvent | HeartbeatEvent;

// ─── Stats / Dashboard ───────────────────────────────────────

export interface DashboardStats {
  total_today: number;
  active_cameras: number;
  detections_per_hour: number;
  peak_hour?: string;
}

export interface HourlyDataPoint {
  hour: string;
  count: number;
}

// ─── Input Manager ───────────────────────────────────────────

export type JobStatus = "queued" | "processing" | "done" | "error";

export interface UploadJob {
  job_id: string;
  status: JobStatus;
  camera_id: string;
  filename: string;
  size_bytes: number;
  progress?: number;
  estimated_duration_sec?: number;
  error?: string;
}

export interface RTSPStream {
  camera_id: string;
  rtsp_url: string;
  label?: string;
  status: "live" | "offline" | "error";
  resolution?: string;
  fps?: number;
}

export interface RTSPTestResult {
  reachable: boolean;
  latency_ms?: number;
  resolution?: string;
  fps?: number;
  error?: string;
}

// ─── Camera ──────────────────────────────────────────────────

export interface Camera {
  id: string;
  name: string;
  location?: string;
  status: "online" | "offline";
  stream_url?: string;
}
