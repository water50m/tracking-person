import { NextRequest } from "next/server";

export async function GET(
  request: NextRequest,
  { params }: { params: { video_id: string } }
) {
  const backendUrl = process.env.AI_BACKEND_URL ?? "http://localhost:8000";
  const { video_id } = params;

  const upstream = await fetch(`${backendUrl}/api/video/videos/${video_id}/stream`, {
    headers: {
      // Forward range requests so HTML5 video can seek efficiently
      ...(request.headers.get("range")
        ? { range: request.headers.get("range") as string }
        : {}),
    },
  });

  const headers = new Headers(upstream.headers);

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers,
  });
}
