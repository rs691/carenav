import type { ChatRequest, ChatResponse } from "./types"

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export async function postChat(
  body: ChatRequest,
  options?: { tenantId?: string; accessToken?: string | null },
): Promise<ChatResponse> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  }

  if (options?.accessToken) {
    headers.Authorization = `Bearer ${options.accessToken}`
  }

  // Dev / fallback tenant header (API still accepts this when JWT has no tenant claim)
  headers["x-tenant-id"] = options?.tenantId || "tenant_bcbs"

  const res = await fetch(`${API_URL}/chat`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
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
