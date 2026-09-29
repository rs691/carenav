"use client"

import { useCallback, useState } from "react"
import Link from "next/link"
import { useParams, useRouter } from "next/navigation"
import { API_URL, ApiError, postChat } from "@/lib/api"
import { useMe } from "@/lib/use-me"
import type { ChatMessage } from "@/lib/types"
import { ChatInput } from "./chat-input"
import { MessageList } from "./message-list"

function newMsgId(): string {
  return `msg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
}

export function ChatUI() {
  const params = useParams<{ chatid?: string }>()
  const sessionId = params.chatid || "default-session"
  const router = useRouter()
  const { me } = useMe()

  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const send = useCallback(
    async (text: string) => {
      setError(null)
      setMessages((prev) => [...prev, { id: newMsgId(), role: "user", content: text }])
      setLoading(true)

      try {
        const data = await postChat({ session_id: sessionId, message: text })
        setMessages((prev) => [
          ...prev,
          {
            id: newMsgId(),
            role: "assistant",
            content: data.reply,
            agentUsed: data.agent_used,
            intent: data.intent,
            phiScrubbed: data.phi_scrubbed,
          },
        ])
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          router.replace("/login")
          router.refresh()
          return
        }
        const message = err instanceof Error ? err.message : "Request failed"
        setError(message)
        setMessages((prev) => [
          ...prev,
          {
            id: newMsgId(),
            role: "assistant",
            content: `Sorry — I couldn’t reach CareNav (${message}). Is the API running (${API_URL})?`,
          },
        ])
      } finally {
        setLoading(false)
      }
    },
    [sessionId, router],
  )

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col bg-stone-50">
      <header className="flex items-center justify-between border-b border-stone-200 bg-white px-4 py-3">
        <div>
          <p className="text-sm font-semibold text-stone-900">
            {me?.first_name ? `Hi, ${me.first_name}` : "CareNav"}
          </p>
          <p className="text-xs text-stone-500">
            {me?.plan_name ?? "Member benefits assistant"}
            {me?.member ? ` · Member ${me.member.member_number}` : ""}
          </p>
        </div>
        <p className="truncate text-xs text-stone-400 max-w-[40%]" title={sessionId}>
          session {sessionId.slice(0, 8)}…
        </p>
      </header>

      {me && !me.linked && (
        <p className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-center text-xs text-amber-900">
          You&apos;re getting general answers.{" "}
          <Link href="/settings" className="font-medium underline underline-offset-2">
            Link your health plan
          </Link>{" "}
          for answers about your coverage.
        </p>
      )}

      <MessageList
        messages={messages}
        loading={loading}
        firstName={me?.first_name ?? null}
        planName={me?.plan_name ?? null}
      />

      {error && (
        <p className="px-4 pb-2 text-center text-xs text-red-600" role="alert">
          {error}
        </p>
      )}

      <ChatInput onSend={send} disabled={loading} />
    </div>
  )
}
