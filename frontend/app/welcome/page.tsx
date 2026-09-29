"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { GalleryVerticalEndIcon } from "lucide-react"
import { skipIdentification } from "@/lib/api"
import { createClient } from "@/lib/supabase/client"
import { useMe } from "@/lib/use-me"
import { MemberLinkForm } from "@/components/member-link-form"
import { ModeToggle } from "@/components/mode-toggle"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

export default function WelcomePage() {
  const router = useRouter()
  const { me } = useMe()
  const [skipping, setSkipping] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function enterApp() {
    router.replace("/")
    router.refresh()
  }

  async function skip() {
    setError(null)
    setSkipping(true)
    try {
      await skipIdentification()
      enterApp()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong")
      setSkipping(false)
    }
  }

  async function signOut() {
    await createClient().auth.signOut()
    router.replace("/login")
    router.refresh()
  }

  const firstName = me?.first_name

  return (
    <div className="relative flex min-h-svh flex-col items-center justify-center gap-6 bg-muted p-6 md:p-10">
      <div className="absolute top-4 right-4">
        <ModeToggle />
      </div>
      <div className="flex w-full max-w-sm flex-col gap-6">
        <div className="flex items-center gap-2 self-center font-medium">
          <div className="flex size-6 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <GalleryVerticalEndIcon className="size-4" />
          </div>
          CareNav
        </div>
        <Card>
          <CardHeader className="text-center">
            <CardTitle className="text-xl">
              {firstName ? `Welcome, ${firstName}!` : "Welcome to CareNav"}
            </CardTitle>
            <CardDescription>
              Let&apos;s find your health plan so answers are about your coverage.
              Grab your member ID card.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <MemberLinkForm
              onLinked={enterApp}
              secondaryAction={
                <Button
                  type="button"
                  variant="ghost"
                  disabled={skipping}
                  onClick={skip}
                >
                  {skipping ? "One moment…" : "Skip for now: general answers only"}
                </Button>
              }
            />
            {error && (
              <p className="text-sm text-destructive" role="alert">
                {error}
              </p>
            )}
          </CardContent>
        </Card>
        <p className="text-center text-sm text-muted-foreground">
          {me?.email ? `Signed in as ${me.email}. ` : ""}
          <button
            type="button"
            onClick={signOut}
            className="underline-offset-4 hover:underline"
          >
            Not you? Sign out
          </button>
        </p>
      </div>
    </div>
  )
}
