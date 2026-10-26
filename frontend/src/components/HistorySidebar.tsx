import { useEffect, useState } from 'react'
import { List, Tag, Typography } from 'antd'
import { listRuns } from '../api'
import { formatDateTime, runStatusTag } from '../status'
import type { Run } from '../types'

const REFRESH_MS = 5000

interface Props {
  selectedId: number | null
  onSelect: (id: number) => void
}

export function HistorySidebar({ selectedId, onSelect }: Props) {
  const [runs, setRuns] = useState<Run[]>([])

  useEffect(() => {
    let active = true
    const load = () => {
      listRuns()
        .then((items) => {
          if (active) setRuns(items)
        })
        .catch(() => undefined)
    }
    void load()
    const timer = window.setInterval(load, REFRESH_MS)
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [])

  return (
    <div>
      <Typography.Text
        style={{
          color: 'rgba(255,255,255,0.45)',
          fontSize: 12,
          letterSpacing: 1,
          textTransform: 'uppercase',
        }}
      >
        历史运行
      </Typography.Text>

      <List
        style={{ marginTop: 10 }}
        dataSource={runs}
        locale={{
          emptyText: (
            <span style={{ color: 'rgba(255,255,255,0.35)' }}>暂无运行记录</span>
          ),
        }}
        split={false}
        renderItem={(run) => {
          const tag = runStatusTag(run.status)
          const selected = run.id === selectedId
          return (
            <List.Item
              onClick={() => onSelect(run.id)}
              style={{
                cursor: 'pointer',
                display: 'block',
                padding: '10px 12px',
                marginBottom: 4,
                borderRadius: 8,
                background: selected ? '#1d2f4d' : 'transparent',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Tag color={tag.color} style={{ marginInlineEnd: 0 }}>
                  {tag.label}
                </Tag>
                <Typography.Text style={{ color: '#dbe6ff', fontSize: 12 }}>
                  #{run.id} · {run.rounds} 轮
                </Typography.Text>
              </div>
              <Typography.Text
                ellipsis
                style={{ color: 'rgba(255,255,255,0.72)', fontSize: 12, display: 'block', marginTop: 4 }}
              >
                {run.url}
              </Typography.Text>
              <Typography.Text style={{ color: 'rgba(255,255,255,0.38)', fontSize: 11 }}>
                {formatDateTime(run.created_at)}
              </Typography.Text>
            </List.Item>
          )
        }}
      />
    </div>
  )
}