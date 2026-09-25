"use client"

import { useEffect, useRef } from "react"
import type { ChatMessage } from "@/lib/types"
import { Message } from "./message"

export function MessageList({
  messages,
  loading,
}: {
  messages: ChatMessage[]
  loading: boolean
}) {
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, loading])

  if (messages.length === 0 && !loading) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 text-center">
        <h2 className="text-2xl font-semibold tracking-tight text-stone-900">CareNav</h2>
        <p className="max-w-md text-stone-600">
          Ask about coverage, deductibles, prescriptions, claims, or prior authorizations.
        </p>
        <ul className="mt-2 space-y-1 text-sm text-stone-500">
          <li>“Is my MRI covered?”</li>
          <li>“What’s my deductible?”</li>
          <li>“Is my prescription on the formulary?”</li>
        </ul>
      </div>
    )
  }

  return (
    <div className="flex flex-1 flex-col gap-4 overflow-y-auto px-4 py-6 sm:px-8">
      {messages.map((m) => (
        <Message key={m.id} message={m} />
      ))}
      {loading && (
        <div className="text-sm text-stone-500 animate-pulse">CareNav is checking your plan…</div>
      )}
      <div ref={endRef} />
    </div>
  )
}
