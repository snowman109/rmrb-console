import { Empty, Tag, Timeline, Typography } from 'antd'
import { formatDateTime } from '../status'
import type { RunEvent } from '../types'

const KIND_LABEL: Record<string, string> = {
  round_start: '开始本轮',
  android_id: 'Android ID 变化',
  cold_boot: '冷启动（wipe）',
  chrome_tap: 'Chrome 点击',
  setup_tap: '安装页点击',
  app_tap: 'App 内点击',
  click_ok: '点击下载成功',
  click_fail: '点击下载失败',
  host_download_ok: '宿主机下载完成',
  host_download_fail: '宿主机下载失败（回退 Chrome）',
  install_attempt: '安装尝试',
  channel_status: '渠道状态',
  boot_fail: '模拟器启动失败',
  no_page: '未打开页面',
  no_apk: '未拿到 APK',
  install_fail: '安装失败',
  port_drift: '模拟器端口漂移',
  timeout: '轮次超时',
  canceled: '已取消',
}

const KIND_COLOR: Record<string, string> = {
  click_ok: 'green',
  host_download_ok: 'green',
  channel_status: 'blue',
  click_fail: 'red',
  host_download_fail: 'red',
  boot_fail: 'red',
  no_page: 'red',
  no_apk: 'red',
  install_fail: 'red',
  port_drift: 'red',
  timeout: 'red',
}

function kindColor(kind: string): string {
  return KIND_COLOR[kind] ?? 'gray'
}

interface Props {
  events: RunEvent[]
}

export function EventTimeline({ events }: Props) {
  if (events.length === 0) {
    return <Empty description="暂无事件" />
  }

  const recent = events.slice(-200)

  return (
    <Timeline
      items={recent.map((event) => ({
        color: kindColor(event.kind),
        children: (
          <div>
            <Typography.Text strong style={{ fontSize: 13 }}>
              {KIND_LABEL[event.kind] ?? event.kind}
            </Typography.Text>
            <Tag style={{ marginLeft: 8 }} bordered={false}>
              第 {event.round_no ?? '?'} 轮
            </Tag>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {formatDateTime(event.ts)}
            </Typography.Text>
            {event.message && (
              <div className="mono" style={{ fontSize: 12, color: '#556' }}>
                {event.message}
              </div>
            )}
          </div>
        ),
      }))}
    />
  )
}