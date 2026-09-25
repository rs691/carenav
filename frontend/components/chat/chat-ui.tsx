"use client"

import { useCallback, useState } from "react"
import { useParams } from "next/navigation"
import { postChat } from "@/lib/api"
import { getOrCreateMemberId, getTenantId } from "@/lib/session"
import type { ChatMessage } from "@/lib/types"
import { ChatInput } from "./chat-input"
import { MessageList } from "./message-list"

function newMsgId(): string {
  return `msg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
}

export function ChatUI() {
  const params = useParams<{ chatid?: string }>()
  const sessionId = params.chatid || "default-session"

  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const send = useCallback(
    async (text: string) => {
      setError(null)
      const userMsg: ChatMessage = {
        id: newMsgId(),
        role: "user",
        content: text,
      }
      setMessages((prev) => [...prev, userMsg])
      setLoading(true)

      try {
        let accessToken: string | null =
          typeof window !== "undefined"
            ? window.sessionStorage.getItem("carenav_access_token")
            : null
        let memberId = getOrCreateMemberId()

        try {
          const { createClient } = await import("@/lib/supabase/client")
          if (process.env.NEXT_PUBLIC_SUPABASE_URL) {
            const supabase = createClient()
            const { data } = await supabase.auth.getSession()
            if (data.session?.access_token) {
              accessToken = data.session.access_token
              sessionStorage.setItem("carenav_access_token", accessToken)
            }
            if (data.session?.user?.id) {
              memberId = data.session.user.id
            }
            const tenantClaim =
              (data.session?.user?.app_metadata as { tenant_id?: string } | undefined)
                ?.tenant_id ||
              (data.session?.user?.user_metadata as { tenant_id?: string } | undefined)
                ?.tenant_id
            if (tenantClaim) {
              const { setTenantId } = await import("@/lib/session")
              setTenantId(tenantClaim)
            }
          }
        } catch {
          /* Supabase optional until env is set */
        }

        const data = await postChat(
          {
            member_id: memberId,
            session_id: sessionId,
            message: text,
          },
          {
            tenantId: getTenantId(),
            accessToken,
          },
        )

        const assistantMsg: ChatMessage = {
          id: newMsgId(),
          role: "assistant",
          content: data.reply,
          agentUsed: data.agent_used,
          intent: data.intent,
          phiScrubbed: data.phi_scrubbed,
        }
        setMessages((prev) => [...prev, assistantMsg])
      } catch (err) {
        const message = err instanceof Error ? err.message : "Request failed"
        setError(message)
        setMessages((prev) => [
          ...prev,
          {
            id: newMsgId(),
            role: "assistant",
            content: `Sorry — I couldn’t reach CareNav (${message}). Is the API running (${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"})?`,
          },
        ])
      } finally {
        setLoading(false)
      }
    },
    [sessionId],
  )

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col bg-stone-50">
      <header className="flex items-center justify-between border-b border-stone-200 bg-white px-4 py-3">
        <div>
          <p className="text-sm font-semibold text-stone-900">CareNav</p>
          <p className="text-xs text-stone-500">Member benefits assistant</p>
        </div>
        <p className="truncate text-xs text-stone-400 max-w-[40%]" title={sessionId}>
          session {sessionId.slice(0, 8)}…
        </p>
      </header>

      <MessageList messages={messages} loading={loading} />

      {error && (
        <p className="px-4 pb-2 text-center text-xs text-red-600" role="alert">
          {error}
        </p>
      )}

      <ChatInput onSend={send} disabled={loading} />
    </div>
  )
}
