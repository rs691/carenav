import { createServerClient } from "@supabase/ssr"
import { NextResponse, type NextRequest } from "next/server"

function isValidSupabaseUrl(url: string | undefined): url is string {
  if (!url) return false
  if (url.includes("<") || url.includes(">")) return false
  try {
    const parsed = new URL(url)
    return parsed.protocol === "https:" && parsed.hostname.endsWith(".supabase.co")
  } catch {
    return false
  }
}

export async function updateSession(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request })

  const url = process.env.NEXT_PUBLIC_SUPABASE_URL
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
  // Skip auth client when .env.local still has placeholders like https://<project>.supabase.co
  if (!isValidSupabaseUrl(url) || !key || key.length < 20) {
    return supabaseResponse
  }

  const supabase = createServerClient(url, key, {
    cookies: {
      getAll() {
        return request.cookies.getAll()
      },
      setAll(cookiesToSet) {
        cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value))
        supabaseResponse = NextResponse.next({ request })
        cookiesToSet.forEach(({ name, value, options }) =>
          supabaseResponse.cookies.set(name, value, options),
        )
      },
    },
  })

  const {
    data: { user },
  } = await supabase.auth.getUser()

  const path = request.nextUrl.pathname
  const isPublic =
    path.startsWith("/login") ||
    path.startsWith("/auth") ||
    path.startsWith("/_next") ||
    path === "/favicon.ico"

  const authRequired = process.env.NEXT_PUBLIC_AUTH_REQUIRED === "true"
  if (authRequired && !user && !isPublic) {
    const redirect = request.nextUrl.clone()
    redirect.pathname = "/login"
    redirect.searchParams.set("next", path)
    return NextResponse.redirect(redirect)
  }

  return supabaseResponse
}
