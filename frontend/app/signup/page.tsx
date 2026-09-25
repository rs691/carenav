"use client"

import Link from "next/link"
import { GalleryVerticalEndIcon } from "lucide-react"
import { SignupForm } from "@/components/signup-form"
import { ModeToggle } from "@/components/mode-toggle"

export default function SignupPage() {
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
        <SignupForm />
      </div>
    </div>
  )
}
