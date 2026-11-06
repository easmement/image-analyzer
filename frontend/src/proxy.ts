import { NextResponse, type NextRequest } from "next/server";

// DNS-rebinding defence, first layer (the backend checks too: core/localhost_only.py).
// A page on evil.example can re-point its domain at 127.0.0.1 and call this server from the
// browser. Browsers never let scripts set Host, so it still names the attacker's domain; reject it
// here, before the /api rewrite forwards anything. (Headers like X-Forwarded-Host *can* be set by
// scripts, so the backend can't rely on those alone.)
const ALLOWED_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"]);

export function proxy(request: NextRequest) {
  const host = request.headers.get("host") ?? "";
  let hostname = "";
  try {
    hostname = new URL(`http://${host}`).hostname;
  } catch {}
  if (!ALLOWED_HOSTS.has(hostname)) {
    return NextResponse.json({ detail: `Requests must come from localhost, not '${hostname}'` }, { status: 403 });
  }
  return NextResponse.next();
}
