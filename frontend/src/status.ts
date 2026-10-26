export const TERMINAL_RUN_STATUSES = new Set([
  'succeeded',
  'failed',
  'canceled',
  'interrupted',
])

export const RUN_STATUS_TAG: Record<string, { color: string; label: string }> = {
  queued: { color: 'default', label: '排队中' },
  running: { color: 'processing', label: '运行中' },
  succeeded: { color: 'success', label: '已完成' },
  failed: { color: 'error', label: '已失败' },
  canceled: { color: 'warning', label: '已取消' },
  interrupted: { color: 'default', label: '已中断' },
}

const ROUND_STATUS_COLOR: Record<string, string> = {
  OK: 'green',
  OPEN_NO_CHANNEL: 'orange',
  OPEN_FAIL: 'red',
  BOOT_FAIL: 'volcano',
  NO_PAGE: 'volcano',
  NO_APK: 'volcano',
  CLICK_FAIL: 'volcano',
  INSTALL_FAIL: 'volcano',
  CSV_MISSING: 'magenta',
  skipped: 'default',
}

export function roundStatusCode(status: string | null | undefined): string {
  if (!status) return ''
  return status.split(':', 1)[0]
}

export function roundStatusColor(status: string | null | undefined): string {
  const code = roundStatusCode(status)
  if (!code) return 'default'
  return ROUND_STATUS_COLOR[code] ?? 'default'
}

export function runStatusTag(status: string): { color: string; label: string } {
  return RUN_STATUS_TAG[status] ?? { color: 'default', label: status }
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString('zh-CN', { hour12: false })
}