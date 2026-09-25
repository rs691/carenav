import type { ChatMessage } from "@/lib/types"

export function Message({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user"

  return (
    <div className={`flex w-full ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-2xl px-4 py-3 text-[15px] leading-relaxed ${
          isUser
            ? "bg-teal-700 text-white"
            : "bg-stone-100 text-stone-900 border border-stone-200"
        }`}
      >
        <p className="whitespace-pre-wrap">{message.content}</p>
        {!isUser && (message.agentUsed || message.intent) && (
          <p className="mt-2 text-xs text-stone-500">
            {[message.agentUsed, message.intent, message.phiScrubbed ? "PHI scrubbed" : null]
              .filter(Boolean)
              .join(" · ")}
          </p>
        )}
      </div>
    </div>
  )
}
