import { createServerClient } from "@supabase/ssr"
import { NextResponse, type NextRequest } from "next/server"

// Set once a browser has signed in, so returning visitors land on sign-in
// instead of sign-up.
const HAS_ACCOUNT_COOKIE = "carenav_has_account"

const AUTH_PAGES = ["/login", "/signup"]
const WELCOME_PAGE = "/welcome"

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

function matches(path: string, prefix: string) {
  return path === prefix || path.startsWith(`${prefix}/`)
}

function redirectTo(
  request: NextRequest,
  pathname: string,
  from: NextResponse,
  next?: string,
) {
  const url = request.nextUrl.clone()
  url.pathname = pathname
  url.search = ""
  if (next && next !== "/") url.searchParams.set("next", next)
  const response = NextResponse.redirect(url)
  // Keep any refreshed auth cookies from the Supabase client.
  from.cookies.getAll().forEach((cookie) => response.cookies.set(cookie))
  return response
}

export async function updateSession(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request })
  const path = request.nextUrl.pathname
  const onAuthPage = AUTH_PAGES.some((p) => matches(path, p))
  const onCallback = matches(path, "/auth")

  const url = process.env.NEXT_PUBLIC_SUPABASE_URL
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
  if (!isValidSupabaseUrl(url) || !key || key.length < 20) {
    // Without Supabase nobody can sign in; the login page reports the config error.
    return onAuthPage || onCallback
      ? supabaseResponse
      : redirectTo(request, "/login", supabaseResponse)
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

  if (onCallback) return supabaseResponse

  if (!user) {
    if (onAuthPage) return supabaseResponse
    const returning = request.cookies.has(HAS_ACCOUNT_COOKIE)
    return redirectTo(
      request,
      returning ? "/login" : "/signup",
      supabaseResponse,
      path + request.nextUrl.search,
    )
  }

  supabaseResponse.cookies.set(HAS_ACCOUNT_COOKIE, "1", {
    path: "/",
    maxAge: 60 * 60 * 24 * 365,
    sameSite: "lax",
  })

  const onboarded = Boolean(
    (user.app_metadata as { onboarded?: boolean } | undefined)?.onboarded,
  )
  const onWelcome = matches(path, WELCOME_PAGE)

  if (!onboarded && !onWelcome) {
    return redirectTo(request, WELCOME_PAGE, supabaseResponse)
  }
  if (onboarded && (onAuthPage || onWelcome)) {
    return redirectTo(request, "/", supabaseResponse)
  }

  return supabaseResponse
}
