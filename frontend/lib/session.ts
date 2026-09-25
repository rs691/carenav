const MEMBER_KEY = "carenav_member_id"
const TENANT_KEY = "carenav_tenant_id"
const DEFAULT_TENANT = "tenant_bcbs"

function newId(): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID()
  }
  return `id_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`
}

export function getOrCreateMemberId(): string {
  if (typeof window === "undefined") return "member_anonymous"
  let id = localStorage.getItem(MEMBER_KEY)
  if (!id) {
    id = newId()
    localStorage.setItem(MEMBER_KEY, id)
  }
  return id
}

export function getTenantId(): string {
  if (typeof window === "undefined") return DEFAULT_TENANT
  return localStorage.getItem(TENANT_KEY) || DEFAULT_TENANT
}

export function setTenantId(tenantId: string): void {
  if (typeof window === "undefined") return
  localStorage.setItem(TENANT_KEY, tenantId)
}

export function createChatId(): string {
  return newId()
}
