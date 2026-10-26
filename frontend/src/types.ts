export interface Config {
  sdk_root: string
  script_path: string
  default_url: string
  default_avd: string
  default_rounds: number
}

export type RunStatus =
  | 'queued'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'canceled'
  | 'interrupted'

export interface Run {
  id: number
  url: string
  rounds: number
  avd: string | null
  serial: string | null
  pkg: string | null
  plan: string | null
  status: RunStatus
  exit_code: number | null
  error: string | null
  sdk_root: string | null
  script_path: string | null
  model: string | null
  qemu: string | null
  out_dir: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export interface RoundRow {
  id: number
  run_id: number
  round_no: number
  action: string | null
  android_id_before: string | null
  android_id_after: string | null
  public_ip: string | null
  clicked_at: string | null
  click_url: string | null
  apk_url: string | null
  install_at: string | null
  open_at: string | null
  installer: string | null
  first_install: string | null
  channel: string | null
  app_version: string | null
  status: string | null
  apk_src: string | null
  log_excerpt: string | null
  source: string | null
}

export interface RunEvent {
  id: number
  run_id: number
  round_no: number | null
  ts: string
  kind: string
  message: string | null
}

export interface LogLine {
  id: number
  run_id: number
  seq: number
  ts: string
  stream: string
  line: string
}

export interface RunDetail {
  run: Run
  counts: Record<string, number>
}