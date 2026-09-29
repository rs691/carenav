import { createClient } from "@/lib/supabase/client"
import type { ChatRequest, ChatResponse, Me } from "./types"

export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function accessToken(): Promise<string> {
  const { data } = await createClient().auth.getSession()
  const token = data.session?.access_token
  if (!token) throw new ApiError(401, "Please sign in again")
  return token
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${await accessToken()}`,
      ...init.headers,
    },
  })

  if (!res.ok) {
    let detail = res.statusText
    try {
      const data = await res.json()
      detail = data.detail || JSON.stringify(data)
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail)
  }

  return res.json()
}

// The API writes identity into Supabase app_metadata; refresh so the next
// token carries the new tenant / member claims.
async function refreshClaims() {
  await createClient().auth.refreshSession()
}

export function postChat(body: ChatRequest): Promise<ChatResponse> {
  return request("/chat", { method: "POST", body: JSON.stringify(body) })
}

export function getMe(): Promise<Me> {
  return request("/me")
}

export async function verifyMember(input: {
  member_number?: string
  group_number: string
}): Promise<{ linked: boolean; tenant_id: string; plan_name: string }> {
  const result = await request<{ linked: boolean; tenant_id: string; plan_name: string }>(
    "/me/member",
    { method: "POST", body: JSON.stringify(input) },
  )
  await refreshClaims()
  return result
}

export async function skipIdentification(): Promise<void> {
  await request("/me/skip", { method: "POST" })
  await refreshClaims()
}

export async function unlinkMember(): Promise<void> {
  await request("/me/member", { method: "DELETE" })
  await refreshClaims()
}
