import { useCallback, useEffect, useRef, useState } from 'react'
import { getRounds, getRun } from '../api'
import type { RoundRow, Run } from '../types'

const POLL_MS = 2000
const TERMINAL = new Set(['succeeded', 'failed', 'canceled', 'interrupted'])

export interface RunPollingState {
  run: Run | null
  counts: Record<string, number>
  rounds: RoundRow[]
  refresh: () => Promise<void>
}

export function useRunPolling(runId: number | null): RunPollingState {
  const [run, setRun] = useState<Run | null>(null)
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [rounds, setRounds] = useState<RoundRow[]>([])
  const statusRef = useRef<string | null>(null)

  const refresh = useCallback(async () => {
    if (runId == null) return
    const [detail, rows] = await Promise.all([getRun(runId), getRounds(runId)])
    statusRef.current = detail.run.status
    setRun(detail.run)
    setCounts(detail.counts)
    setRounds(rows)
  }, [runId])

  useEffect(() => {
    if (runId == null) {
      statusRef.current = null
      setRun(null)
      setCounts({})
      setRounds([])
      return
    }

    let timer: number | undefined
    const tick = async () => {
      try {
        await refresh()
      } catch {
        return
      }
      if (statusRef.current && TERMINAL.has(statusRef.current) && timer !== undefined) {
        window.clearInterval(timer)
      }
    }

    void tick()
    timer = window.setInterval(() => void tick(), POLL_MS)
    return () => {
      if (timer !== undefined) window.clearInterval(timer)
    }
  }, [runId, refresh])

  return { run, counts, rounds, refresh }
}