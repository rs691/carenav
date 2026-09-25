"use client"

import { useEffect, useState } from "react"
import { getTenantId, setTenantId } from "@/lib/session"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Field, FieldLabel } from "@/components/ui/field"
import { ModeToggle } from "@/components/mode-toggle"

const TENANTS = [
  { id: "tenant_bcbs", label: "BlueCross Premier PPO" },
  { id: "tenant_medicaid", label: "Illinois Medicaid" },
  { id: "tenant_employer", label: "Acme Corp Benefits" },
]

export default function SettingsPage() {
  const [tenant, setTenant] = useState("tenant_bcbs")
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    setTenant(getTenantId())
  }, [])

  function save() {
    setTenantId(tenant)
    setSaved(true)
    setTimeout(() => setSaved(false), 1500)
  }

  return (
    <div className="mx-auto flex w-full max-w-lg flex-col gap-6 p-6 md:p-8">
      <Card>
        <CardHeader>
          <CardTitle>Settings</CardTitle>
          <CardDescription>
            Dev tenant selection used when JWT has no tenant claim.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-6">
          <Field>
            <FieldLabel htmlFor="tenant">Tenant</FieldLabel>
            <select
              id="tenant"
              value={tenant}
              onChange={(e) => setTenant(e.target.value)}
              className="h-8 w-full rounded-lg border border-input bg-background px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
            >
              {TENANTS.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.label}
                </option>
              ))}
            </select>
          </Field>
          <Field>
            <FieldLabel>Appearance</FieldLabel>
            <div className="flex items-center gap-3">
              <ModeToggle />
              <span className="text-sm text-muted-foreground">
                Light / dark / system
              </span>
            </div>
          </Field>
          <Button type="button" onClick={save} className="w-fit">
            Save
          </Button>
          {saved && (
            <p className="text-sm text-muted-foreground" role="status">
              Saved.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
