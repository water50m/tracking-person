import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.AI_BACKEND_URL ?? "http://localhost:8000";

export async function POST(req: NextRequest) {
    try {
        const form = await req.formData();
        const res = await fetch(`${BACKEND}/api/video/analyze/youtube`, {
            method: "POST",
            body: form,
        });
        const data = await res.json();
        if (!res.ok) return NextResponse.json(data, { status: res.status });
        return NextResponse.json(data);
    } catch (e) {
        return NextResponse.json({ error: String(e) }, { status: 500 });
    }
}
