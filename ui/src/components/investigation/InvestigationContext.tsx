"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useReducer,
  useRef,
} from "react";
import type {
  ClothingClass,
  ClothingColor,
  SearchFilters,
  SearchResult,
  AttributeDetectionResult,
} from "@/types";
import { API } from "@/lib/api"; // FastAPI base URL จาก .env.local (NEXT_PUBLIC_API_URL)

// ─── State ────────────────────────────────────────────────────

interface InvestigationState {
  filters: SearchFilters;
  results: SearchResult[];
  total: number;
  page: number;
  hasMore: boolean;
  isSearching: boolean;
  isLoadingMore: boolean;
  autoFillImage: string | null;
  autoFillStatus: "idle" | "analyzing" | "done" | "error";
  autoFillResult: AttributeDetectionResult | null;
  // Trace modal
  traceTarget: SearchResult | null;
  // Image modal
  imageTarget: SearchResult | null;
  // Detection detail
  detectionDetail: any | null;
}

const INITIAL_FILTERS: SearchFilters = {
  clothing: [],
  colors: [],
  logic: "OR",
  threshold: 0.65,
  camera_id: undefined,
  video_id: undefined,
  start_time: undefined,
  end_time: undefined,
};

const INITIAL_STATE: InvestigationState = {
  filters: INITIAL_FILTERS,
  results: [],
  total: 0,
  page: 1,
  hasMore: false,
  isSearching: false,
  isLoadingMore: false,
  autoFillImage: null,
  autoFillStatus: "idle",
  autoFillResult: null,
  traceTarget: null,
  imageTarget: null,
  detectionDetail: null,
};

// ─── Actions ──────────────────────────────────────────────────

type Action =
  | { type: "SET_CLOTHING"; payload: ClothingClass[] }
  | { type: "TOGGLE_CLOTHING"; payload: ClothingClass }
  | { type: "SET_COLORS"; payload: ClothingColor[] }
  | { type: "TOGGLE_COLOR"; payload: ClothingColor }
  | { type: "SET_LOGIC"; payload: "OR" | "AND" }
  | { type: "SET_THRESHOLD"; payload: number }
  | { type: "SET_CAMERA"; payload: string | undefined }
  | { type: "SET_VIDEO"; payload: string | undefined }
  | { type: "SET_START_TIME"; payload: string | undefined }
  | { type: "SET_END_TIME"; payload: string | undefined }
  | { type: "RESET_FILTERS" }
  | { type: "SEARCH_START" }
  | { type: "SEARCH_SUCCESS"; payload: { results: SearchResult[]; total: number; hasMore: boolean } }
  | { type: "SEARCH_ERROR" }
  | { type: "LOAD_MORE_START" }
  | { type: "LOAD_MORE_SUCCESS"; payload: { results: SearchResult[]; hasMore: boolean } }
  | { type: "SET_AUTOFILL_IMAGE"; payload: string }
  | { type: "AUTOFILL_START" }
  | { type: "AUTOFILL_SUCCESS"; payload: AttributeDetectionResult }
  | { type: "AUTOFILL_ERROR" }
  | { type: "CLEAR_AUTOFILL" }
  | { type: "OPEN_TRACE"; payload: SearchResult }
  | { type: "CLOSE_TRACE" }
  | { type: "OPEN_IMAGE"; payload: SearchResult }
  | { type: "CLOSE_IMAGE" }
  | { type: "SET_DETECTION_DETAIL"; payload: any | null };

function reducer(state: InvestigationState, action: Action): InvestigationState {
  switch (action.type) {
    case "TOGGLE_CLOTHING": {
      const has = state.filters.clothing.includes(action.payload);
      return {
        ...state,
        filters: {
          ...state.filters,
          clothing: has
            ? state.filters.clothing.filter((c) => c !== action.payload)
            : [...state.filters.clothing, action.payload],
        },
      };
    }
    case "SET_CLOTHING":
      return { ...state, filters: { ...state.filters, clothing: action.payload } };
    case "TOGGLE_COLOR": {
      const has = state.filters.colors.includes(action.payload);
      return {
        ...state,
        filters: {
          ...state.filters,
          colors: has
            ? state.filters.colors.filter((c) => c !== action.payload)
            : [...state.filters.colors, action.payload],
        },
      };
    }
    case "SET_COLORS":
      return { ...state, filters: { ...state.filters, colors: action.payload } };
    case "SET_LOGIC":
      return { ...state, filters: { ...state.filters, logic: action.payload } };
    case "SET_THRESHOLD":
      return { ...state, filters: { ...state.filters, threshold: action.payload } };
    case "SET_CAMERA":
      return { ...state, filters: { ...state.filters, camera_id: action.payload, video_id: undefined } };
    case "SET_VIDEO":
      return { ...state, filters: { ...state.filters, video_id: action.payload } };
    case "SET_START_TIME":
      return { ...state, filters: { ...state.filters, start_time: action.payload } };
    case "SET_END_TIME":
      return { ...state, filters: { ...state.filters, end_time: action.payload } };
    case "RESET_FILTERS":
      return { ...state, filters: INITIAL_FILTERS, autoFillImage: null, autoFillStatus: "idle", autoFillResult: null };
    case "SEARCH_START":
      return { ...state, isSearching: true, page: 1 };
    case "SEARCH_SUCCESS":
      return {
        ...state,
        isSearching: false,
        results: action.payload.results,
        total: action.payload.total,
        hasMore: action.payload.hasMore,
        page: 1,
      };
    case "SEARCH_ERROR":
      return { ...state, isSearching: false };
    case "LOAD_MORE_START":
      return { ...state, isLoadingMore: true };
    case "LOAD_MORE_SUCCESS":
      return {
        ...state,
        isLoadingMore: false,
        results: [...state.results, ...action.payload.results],
        hasMore: action.payload.hasMore,
        page: state.page + 1,
      };
    case "SET_AUTOFILL_IMAGE":
      return { ...state, autoFillImage: action.payload };
    case "AUTOFILL_START":
      return { ...state, autoFillStatus: "analyzing" };
    case "AUTOFILL_SUCCESS":
      return { ...state, autoFillStatus: "done", autoFillResult: action.payload };
    case "AUTOFILL_ERROR":
      return { ...state, autoFillStatus: "error" };
    case "CLEAR_AUTOFILL":
      return { ...state, autoFillImage: null, autoFillStatus: "idle", autoFillResult: null };
    case "OPEN_TRACE":
      return { ...state, traceTarget: action.payload };
    case "CLOSE_TRACE":
      return { ...state, traceTarget: null };
    case "OPEN_IMAGE":
      return { ...state, imageTarget: action.payload };
    case "CLOSE_IMAGE":
      return { ...state, imageTarget: null };
    case "SET_DETECTION_DETAIL":
      return { ...state, detectionDetail: action.payload };
    default:
      return state;
  }
}

// ─── Context ──────────────────────────────────────────────────

interface InvestigationContextValue {
  state: InvestigationState;
  dispatch: React.Dispatch<Action>;
  // Helper actions
  toggleClothing: (c: ClothingClass) => void;
  toggleColor: (c: ClothingColor) => void;
  setLogic: (l: "OR" | "AND") => void;
  setThreshold: (t: number) => void;
  setCamera: (id: string | undefined) => void;
  setVideo: (id: string | undefined) => void;
  setTimeRange: (start?: string, end?: string) => void;
  resetFilters: () => void;
  runSearch: () => void;
  loadMore: () => void;
  submitAutoFill: (file: File) => void;
  clearAutoFill: () => void;
  openTrace: (result: SearchResult) => void;
  closeTrace: () => void;
  openImage: (result: SearchResult) => void;
  closeImage: () => void;
  setDetectionDetail: (detail: any | null) => void;
}

const InvestigationContext = createContext<InvestigationContextValue | null>(null);

export function useInvestigation() {
  const ctx = useContext(InvestigationContext);
  if (!ctx) throw new Error("useInvestigation must be used inside InvestigationProvider");
  return ctx;
}

// ─── Provider ────────────────────────────────────────────────

export function InvestigationProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE);
  const searchAbortRef = useRef<AbortController | null>(null);

  // ── Auto search on mount ───────────────────────────────────
  useEffect(() => {
    // Auto search with default filters on component mount
    const timer = setTimeout(() => {
      runSearch();
    }, 500); // Small delay to ensure component is mounted

    return () => clearTimeout(timer);
  }, []);

  // ── Fetch detection detail when imageTarget changes ────────────────────────────────────
  useEffect(() => {
    if (!state.imageTarget) {
      dispatch({ type: "SET_DETECTION_DETAIL", payload: null });
      return;
    }

    const fetchDetectionDetail = async () => {
      try {
        // เรียก FastAPI โดยตรง — ดึง detection detail
        const response = await fetch(`${API}/api/detections/${encodeURIComponent(state.imageTarget!.id)}`);
        if (!response.ok) {
          throw new Error("Failed to fetch detection details");
        }
        const data = await response.json();
        dispatch({ type: "SET_DETECTION_DETAIL", payload: data });
      } catch (error) {
        console.error("Error fetching detection detail:", error);
        dispatch({ type: "SET_DETECTION_DETAIL", payload: null });
      }
    };

    fetchDetectionDetail();
  }, [state.imageTarget]);

  // ── Search ──────────────────────────────────────────────────
  const runSearch = useCallback(async () => {
    searchAbortRef.current?.abort();
    const controller = new AbortController();
    searchAbortRef.current = controller;

    dispatch({ type: "SEARCH_START" });

    try {
      const params = buildParams(state.filters, 1);
      // เรียก FastAPI /api/search/persons โดยตรง — ไม่ผ่าน Next.js transform layer
      const res = await fetch(`${API}/api/search/persons?${params}`, {
        signal: controller.signal,
      });
      if (!res.ok) throw new Error("Search failed");
      const data = await res.json();
      dispatch({
        type: "SEARCH_SUCCESS",
        payload: {
          results: data.results,
          total: data.total,
          hasMore: data.has_more,
        },
      });
    } catch (e: unknown) {
      if (e instanceof Error && e.name !== "AbortError") {
        dispatch({ type: "SEARCH_ERROR" });
      }
    }
  }, [state.filters]);

  // ── Load more (infinite scroll) ──────────────────────────────
  const loadMore = useCallback(async () => {
    if (state.isLoadingMore || !state.hasMore) return;
    dispatch({ type: "LOAD_MORE_START" });

    try {
      const params = buildParams(state.filters, state.page + 1);
      // เรียก FastAPI โดยตรง
      const res = await fetch(`${API}/api/search/persons?${params}`);
      if (!res.ok) throw new Error("Load more failed");
      const data = await res.json();
      dispatch({
        type: "LOAD_MORE_SUCCESS",
        payload: { results: data.results, hasMore: data.has_more },
      });
    } catch {
      dispatch({ type: "LOAD_MORE_START" }); // reset flag
    }
  }, [state.filters, state.page, state.isLoadingMore, state.hasMore]);

  // ── Auto-fill ────────────────────────────────────────────────
  const submitAutoFill = useCallback(async (file: File) => {
    // Preview
    const dataUrl = await fileToDataUrl(file);
    dispatch({ type: "SET_AUTOFILL_IMAGE", payload: dataUrl });
    dispatch({ type: "AUTOFILL_START" });

    try {
      const form = new FormData();
      form.append("image", file);
      const res = await fetch("/api/search/detect-attributes", {
        method: "POST",
        body: form,
      });
      if (!res.ok) throw new Error("Detection failed");
      const result: AttributeDetectionResult = await res.json();

      dispatch({ type: "AUTOFILL_SUCCESS", payload: result });

      // ── Auto-apply detected attributes to filters ──
      if (result.class && result.class !== "Unknown") {
        dispatch({ type: "SET_CLOTHING", payload: [result.class] });
      }
      if (result.color && result.color !== "Unknown") {
        const colors: ClothingColor[] = [result.color];
        if (result.secondary_color && result.secondary_color !== "Unknown") {
          colors.push(result.secondary_color);
        }
        dispatch({ type: "SET_COLORS", payload: colors });
      }

      // Auto-search immediately after fill
      // (use a small delay so state can settle)
      setTimeout(() => {
        dispatch({ type: "SEARCH_START" });
        const params = buildParams(
          {
            ...INITIAL_FILTERS,
            clothing: result.class !== "Unknown" ? [result.class] : [],
            colors: result.color !== "Unknown" ? [result.color] : [],
          },
          1
        );
        // เรียก FastAPI โดยตรง — auto-search หลัง autofill
        fetch(`${API}/api/search/persons?${params}`)
          .then((r) => r.json())
          .then((data) =>
            dispatch({
              type: "SEARCH_SUCCESS",
              payload: { results: data.results, total: data.total, hasMore: data.has_more },
            })
          )
          .catch(() => dispatch({ type: "SEARCH_ERROR" }));
      }, 300);
    } catch {
      dispatch({ type: "AUTOFILL_ERROR" });
    }
  }, []);

  // ─── Utils ────────────────────────────────────────────────────

  function buildParams(filters: SearchFilters, page: number): string {
    const p = new URLSearchParams();
    filters.clothing.forEach((c) => p.append("clothing[]", c));
    filters.colors.forEach((c) => p.append("colors[]", c));
    p.set("logic", filters.logic);
    p.set("threshold", filters.threshold.toString());
    p.set("page", page.toString());
    p.set("limit", "24");
    if (filters.camera_id) p.set("camera_id", filters.camera_id);
    if (filters.video_id) p.set("video_id", filters.video_id);
    if (filters.start_time) p.set("start_time", filters.start_time);
    if (filters.end_time) p.set("end_time", filters.end_time);

    return p.toString();
  }

  function fileToDataUrl(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
      const r = new FileReader();
      r.onload = () => resolve(r.result as string);
      r.onerror = () => reject(new Error("Read failed"));
      r.readAsDataURL(file);
    });
  }

  const value: InvestigationContextValue = {
    state,
    dispatch,
    toggleClothing: (c) => dispatch({ type: "TOGGLE_CLOTHING", payload: c }),
    toggleColor: (c) => dispatch({ type: "TOGGLE_COLOR", payload: c }),
    setLogic: (l) => dispatch({ type: "SET_LOGIC", payload: l }),
    setThreshold: (t) => dispatch({ type: "SET_THRESHOLD", payload: t }),
    setCamera: (id) => dispatch({ type: "SET_CAMERA", payload: id }),
    setVideo: (id) => dispatch({ type: "SET_VIDEO", payload: id }),
    setTimeRange: (s, e) => {
      dispatch({ type: "SET_START_TIME", payload: s });
      dispatch({ type: "SET_END_TIME", payload: e });
    },
    resetFilters: () => dispatch({ type: "RESET_FILTERS" }),
    runSearch,
    loadMore,
    submitAutoFill,
    clearAutoFill: () => dispatch({ type: "CLEAR_AUTOFILL" }),
    openTrace: (result) => dispatch({ type: "OPEN_TRACE", payload: result }),
    closeTrace: () => dispatch({ type: "CLOSE_TRACE" }),
    openImage: (result) => dispatch({ type: "OPEN_IMAGE", payload: result }),
    closeImage: () => dispatch({ type: "CLOSE_IMAGE" }),
    setDetectionDetail: (detail) => dispatch({ type: "SET_DETECTION_DETAIL", payload: detail }),
  };

  return (
    <InvestigationContext.Provider value={value}>
      {children}
    </InvestigationContext.Provider>
  );
}