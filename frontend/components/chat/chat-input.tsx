"use client"

import { useState, type FormEvent, type KeyboardEvent } from "react"

export function ChatInput({
  onSend,
  disabled,
}: {
  onSend: (message: string) => void
  disabled?: boolean
}) {
  const [value, setValue] = useState("")

  function submit() {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setValue("")
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    submit()
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <form onSubmit={onSubmit} className="border-t border-stone-200 bg-white p-4">
      <div className="mx-auto flex max-w-3xl gap-3">
        <textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={onKeyDown}
          rows={1}
          disabled={disabled}
          placeholder="Ask about your benefits…"
          className="min-h-[48px] flex-1 resize-none rounded-xl border border-stone-300 bg-stone-50 px-4 py-3 text-[15px] text-stone-900 outline-none focus:border-teal-600 focus:ring-1 focus:ring-teal-600 disabled:opacity-60"
        />
        <button
          type="submit"
          disabled={disabled || !value.trim()}
          className="rounded-xl bg-teal-700 px-5 text-sm font-medium text-white transition hover:bg-teal-800 disabled:opacity-50"
        >
          Send
        </button>
      </div>
    </form>
  )
}
