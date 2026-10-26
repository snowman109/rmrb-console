import { useEffect, useState } from 'react'
import {
  Alert,
  Button,
  Col,
  Empty,
  Progress,
  Row,
  Space,
  Statistic,
  Tag,
  Typography,
} from 'antd'
import type { Run } from '../types'

const TERMINAL = new Set(['succeeded', 'failed', 'canceled', 'interrupted'])
const ENV_FAILURE_STATUSES = [
  'BOOT_FAIL', 'NO_PAGE', 'NO_APK', 'CLICK_FAIL', 'INSTALL_FAIL', 'CSV_MISSING',
]

const RUN_TAG: Record<string, { color: string; label: string }> = {
  queued: { color: 'default', label: '排队中' },
  running: { color: 'processing', label: '运行中' },
  succeeded: { color: 'success', label: '已完成' },
  failed: { color: 'error', label: '已失败' },
  canceled: { color: 'warning', label: '已取消' },
  interrupted: { color: 'default', label: '已中断' },
}

function formatDuration(start: string | null, end: string | null): string {
  if (!start) return '—'
  const startMs = new Date(start).getTime()
  const endMs = end ? new Date(end).getTime() : Date.now()
  const seconds = Math.max(0, Math.floor((endMs - startMs) / 1000))
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const rest = seconds % 60
  if (hours > 0) return `${hours}h ${minutes}m ${rest}s`
  return `${minutes}m ${rest}s`
}

interface Props {
  run: Run | null
  counts: Record<string, number>
  onCancel: () => void
}

export function RunOverview({ run, counts, onCancel }: Props) {
  const [, setTick] = useState(0)

  useEffect(() => {
    if (!run || TERMINAL.has(run.status)) return
    const timer = window.setInterval(() => setTick((v) => v + 1), 1000)
    return () => window.clearInterval(timer)
  }, [run])

  if (!run) {
    return <Empty description="还没有选择运行" />
  }

  const done = Object.values(counts).reduce((sum, n) => sum + n, 0)
  const failed = ENV_FAILURE_STATUSES.reduce((sum, key) => sum + (counts[key] ?? 0), 0)
  const percent = run.rounds > 0 ? Math.round((done / run.rounds) * 100) : 0
  const tag = RUN_TAG[run.status] ?? { color: 'default', label: run.status }
  const active = run.status === 'queued' || run.status === 'running'

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Space wrap size={12} align="center">
        <Typography.Title level={5} style={{ margin: 0 }}>
          运行 #{run.id}
        </Typography.Title>
        <Tag color={tag.color}>{tag.label}</Tag>
        <Typography.Text type="secondary">
          {run.avd} · {run.serial} · {run.model ?? 'model 未知'}
        </Typography.Text>
        <Button danger size="small" disabled={!active} onClick={onCancel}>
          取消
        </Button>
        <Typography.Text type="secondary">取消后不能续跑</Typography.Text>
      </Space>

      {run.error && <Alert type="error" showIcon message={run.error} />}

      <Row gutter={[16, 16]}>
        <Col xs={12} sm={8} lg={4}>
          <Statistic title="计划轮数" value={run.rounds} />
        </Col>
        <Col xs={12} sm={8} lg={4}>
          <Statistic title="已完成" value={done} />
        </Col>
        <Col xs={12} sm={8} lg={4}>
          <Statistic title="OK" value={counts.OK ?? 0} valueStyle={{ color: '#1f9d55' }} />
        </Col>
        <Col xs={12} sm={8} lg={4}>
          <Statistic
            title="无 channel"
            value={counts.OPEN_NO_CHANNEL ?? 0}
            valueStyle={{ color: '#d9822b' }}
          />
        </Col>
        <Col xs={12} sm={8} lg={4}>
          <Statistic
            title="OPEN_FAIL"
            value={counts.OPEN_FAIL ?? 0}
            valueStyle={{ color: '#d64545' }}
          />
        </Col>
        <Col xs={12} sm={8} lg={4}>
          <Statistic title="环境失败" value={failed} />
        </Col>
        <Col xs={12} sm={8} lg={4}>
          <Statistic title="已用时长" value={formatDuration(run.started_at, run.finished_at)} />
        </Col>
      </Row>

      <Progress
        percent={percent}
        status={run.status === 'failed' ? 'exception' : active ? 'active' : 'normal'}
        format={() => `${done} / ${run.rounds}`}
      />
    </Space>
  )
}