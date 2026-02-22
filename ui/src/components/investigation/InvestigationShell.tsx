"use client";

import { InvestigationProvider } from "./InvestigationContext";
import SearchFilterBar from "./SearchFilterBar";
import ResultsGrid from "./ResultsGrid";
import TraceModal from "./TraceModal";
import ImageModal from "./ImageModal";

/**
 * InvestigationShell
 *
 * Wraps all investigation components in the shared context provider
 * and renders the TraceModal at the top level so it can use the portal overlay.
 *
 * Usage in app/investigation/page.tsx:
 *   import InvestigationShell from "@/components/investigation/InvestigationShell"
 *   <InvestigationShell />
 */
export default function InvestigationShell() {
  return (
    <InvestigationProvider>
      {/* Filter bar */}
      <SearchFilterBar />

      {/* Results */}
      <ResultsGrid />

      {/* Trace modal — rendered outside the grid flow via fixed positioning */}
      <TraceModal />
      
      {/* Image modal — for showing enlarged image with trace/video buttons */}
      <ImageModal />
    </InvestigationProvider>
  );
}