"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"
import { createChatId } from "@/lib/session"

export default function Home() {
  const router = useRouter()

  useEffect(() => {
    const id = createChatId()
    router.replace(`/en/default/chat/${id}`)
  }, [router])

  return (
    <div className="flex flex-1 items-center justify-center text-stone-500">
      Starting a new chat…
    </div>
  )
}
