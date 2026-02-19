import { NextRequest, NextResponse } from "next/server";

/**
 * GET /api/search/results
 *
 * Query params:
 *   - clothing[]   : array of clothing types (Shirt, Jacket, ...)
 *   - colors[]     : array of colors (Red, Black, ...)
 *   - logic        : "OR" | "AND"  (default: "OR")
 *   - threshold    : number 0-1   (color similarity threshold)
 *   - camera_id    : string (optional)
 *   - start_time   : ISO date string (optional)
 *   - end_time     : ISO date string (optional)
 *   - page         : number (default: 1)
 *   - limit        : number (default: 24)
 *
 * Returns: { results: SearchResult[], total: number, page: number, has_more: boolean }
 */
export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;

  const clothing = searchParams.getAll("clothing[]");
  const colors = searchParams.getAll("colors[]");
  const logic = searchParams.get("logic") ?? "OR";
  const threshold = parseFloat(searchParams.get("threshold") ?? "0.7");
  const cameraId = searchParams.get("camera_id");
  const startTime = searchParams.get("start_time");
  const endTime = searchParams.get("end_time");
  const page = parseInt(searchParams.get("page") ?? "1");
  const limit = Math.min(parseInt(searchParams.get("limit") ?? "24"), 100);

  // Validate inputs
  if (clothing.length === 0 && colors.length === 0) {
    return NextResponse.json(
      { error: "At least one clothing type or color is required" },
      { status: 400 }
    );
  }

  if (!["OR", "AND"].includes(logic)) {
    return NextResponse.json(
      { error: "Logic must be OR or AND" },
      { status: 400 }
    );
  }

  try {
    const backendUrl = process.env.AI_BACKEND_URL ?? "http://localhost:8000";

    // Build backend query
    const backendParams = new URLSearchParams();
    clothing.forEach((c) => backendParams.append("clothing[]", c));
    colors.forEach((c) => backendParams.append("colors[]", c));
    backendParams.set("logic", logic);
    backendParams.set("threshold", threshold.toString());
    if (cameraId) backendParams.set("camera_id", cameraId);
    if (startTime) backendParams.set("start_time", startTime);
    if (endTime) backendParams.set("end_time", endTime);
    backendParams.set("page", page.toString());
    backendParams.set("limit", limit.toString());

    const backendRes = await fetch(
      `${backendUrl}/api/search/persons?${backendParams.toString()}`,
      { next: { revalidate: 0 } } // Always fresh
    );

    if (!backendRes.ok) {
      throw new Error(`Backend responded with ${backendRes.status}`);
    }

    const data = await backendRes.json();

    return NextResponse.json({
      results: data.results ?? [],
      total: data.total ?? 0,
      page: data.page ?? page,
      has_more: data.has_more ?? false,
    });
  } catch (err) {
    console.error("[search/results] Error:", err);
    return NextResponse.json(
      { error: "Failed to fetch search results" },
      { status: 500 }
    );
  }
}
