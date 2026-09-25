"use client"

import { Suspense, useEffect } from "react"
import Link from "next/link"
import { GalleryVerticalEndIcon } from "lucide-react"
import { createClient } from "@/lib/supabase/client"
import { LoginForm } from "@/components/login-form"
import { ModeToggle } from "@/components/mode-toggle"

export default function LoginPage() {
  useEffect(() => {
    if (!process.env.NEXT_PUBLIC_SUPABASE_URL) return
    const supabase = createClient()
    supabase.auth.getSession().then(({ data }) => {
      if (data.session?.access_token) {
        sessionStorage.setItem("carenav_access_token", data.session.access_token)
      }
    })
    const { data: sub } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session?.access_token) {
        sessionStorage.setItem("carenav_access_token", session.access_token)
      } else {
        sessionStorage.removeItem("carenav_access_token")
      }
    })
    return () => sub.subscription.unsubscribe()
  }, [])

  return (
    <div className="relative flex min-h-svh flex-col items-center justify-center gap-6 bg-muted p-6 md:p-10">
      <div className="absolute top-4 right-4">
        <ModeToggle />
      </div>
      <div className="flex w-full max-w-sm flex-col gap-6">
        <Link
          href="/"
          className="flex items-center gap-2 self-center font-medium"
        >
          <div className="flex size-6 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <GalleryVerticalEndIcon className="size-4" />
          </div>
          CareNav
        </Link>
        <Suspense
          fallback={
            <div className="text-center text-sm text-muted-foreground">
              Loading…
            </div>
          }
        >
          <LoginForm />
        </Suspense>
      </div>
    </div>
  )
}
