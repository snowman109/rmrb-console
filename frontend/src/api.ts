import type {
  Config,
  LogLine,
  RoundRow,
  Run,
  RunDetail,
  RunEvent,
} from './types'

const BASE = '/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    let detail: unknown = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ?? detail
    } catch {
      /* keep statusText */
    }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return (await res.json()) as T
}

export function getConfig(): Promise<Config> {
  return request<Config>('/config')
}

export function putConfig(patch: Partial<Config>): Promise<Config> {
  return request<Config>('/config', {
    method: 'PUT',
    body: JSON.stringify(patch),
  })
}

export function listAvds(): Promise<string[]> {
  return request<string[]>('/avds')
}

export function createRun(input: {
  url: string
  rounds: number
  avd?: string
}): Promise<{ id: number }> {
  return request<{ id: number }>('/runs', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function listRuns(): Promise<Run[]> {
  return request<Run[]>('/runs')
}

export function getRun(id: number): Promise<RunDetail> {
  return request<RunDetail>(`/runs/${id}`)
}

export function getRounds(id: number): Promise<RoundRow[]> {
  return request<RoundRow[]>(`/runs/${id}/rounds`)
}

export function getEvents(id: number, afterId: number): Promise<RunEvent[]> {
  return request<RunEvent[]>(`/runs/${id}/events?after_id=${afterId}`)
}

export function getLogs(id: number, afterSeq: number): Promise<LogLine[]> {
  return request<LogLine[]>(`/runs/${id}/logs?after_seq=${afterSeq}`)
}

export function cancelRun(id: number): Promise<{ canceled: boolean }> {
  return request<{ canceled: boolean }>(`/runs/${id}/cancel`, { method: 'POST' })
}

export function exportCsvUrl(id: number): string {
  return `${BASE}/runs/${id}/export.csv`
}