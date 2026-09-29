"use client"

import { useCallback, useEffect, useState } from "react"
import { getMe } from "@/lib/api"
import type { Me } from "@/lib/types"

type MeState = { me: Me | null; error: string | null; loading: boolean }

function toError(err: unknown) {
  return err instanceof Error ? err.message : "Couldn't load your profile"
}

export function useMe() {
  const [state, setState] = useState<MeState>({ me: null, error: null, loading: true })

  useEffect(() => {
    let cancelled = false
    getMe().then(
      (me) => !cancelled && setState({ me, error: null, loading: false }),
      (err) => !cancelled && setState((s) => ({ ...s, error: toError(err), loading: false })),
    )
    return () => {
      cancelled = true
    }
  }, [])

  const refresh = useCallback(async () => {
    setState((s) => ({ ...s, loading: true }))
    try {
      setState({ me: await getMe(), error: null, loading: false })
    } catch (err) {
      setState((s) => ({ ...s, error: toError(err), loading: false }))
    }
  }, [])

  return { ...state, refresh }
}
