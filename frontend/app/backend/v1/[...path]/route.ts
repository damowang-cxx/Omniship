import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND_API_BASE_URL = (
  process.env.FRONTEND_API_BASE_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://127.0.0.1:8000"
).replace(/\/$/, "");

const DEFAULT_PROXY_TIMEOUT_MS = Number(
  process.env.FRONTEND_API_PROXY_TIMEOUT_MS ?? 30_000
);
const PLATFORM_UPLOAD_PROXY_TIMEOUT_MS = Number(
  process.env.FRONTEND_PLATFORM_UPLOAD_PROXY_TIMEOUT_MS ?? 10 * 60 * 1000
);

function getProxyTimeoutMs(path: string[], method: string) {
  if (method === "POST" && path.join("/") === "waybill-uploads/file") {
    return PLATFORM_UPLOAD_PROXY_TIMEOUT_MS;
  }
  return DEFAULT_PROXY_TIMEOUT_MS;
}

async function proxy(request: NextRequest, context: { params: { path: string[] } }) {
  const sourceUrl = new URL(request.url);
  const targetUrl = new URL(
    `/api/v1/${context.params.path.join("/")}${sourceUrl.search}`,
    BACKEND_API_BASE_URL
  );
  const controller = new AbortController();
  const timeout = setTimeout(
    () => controller.abort(),
    getProxyTimeoutMs(context.params.path, request.method)
  );

  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("connection");

  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  let response: Response;
  try {
    response = await fetch(targetUrl, {
      method: request.method,
      headers,
      body: hasBody ? await request.arrayBuffer() : undefined,
      cache: "no-store",
      redirect: "manual",
      signal: controller.signal
    });
  } catch (error) {
    const isTimeout = error instanceof Error && error.name === "AbortError";
    return NextResponse.json(
      {
        detail: isTimeout
          ? "Backend request timed out"
          : "Backend service is unavailable"
      },
      { status: isTimeout ? 504 : 502 }
    );
  } finally {
    clearTimeout(timeout);
  }

  const responseHeaders = new Headers(response.headers);
  responseHeaders.delete("content-encoding");
  responseHeaders.delete("content-length");

  return new NextResponse(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: responseHeaders
  });
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const PUT = proxy;
export const DELETE = proxy;
export const OPTIONS = proxy;
