import { useEffect, useRef, useState } from 'react'
import { Collapse, Typography } from 'antd'
import { getLogs } from '../api'
import type { LogLine } from '../types'

const MAX_LINES = 2000

interface Props {
  runId: number | null
  active: boolean
}

export function LogViewer({ runId, active }: Props) {
  const [expanded, setExpanded] = useState(false)
  const [lines, setLines] = useState<LogLine[]>([])
  const lastSeq = useRef(-1)
  const preRef = useRef<HTMLPreElement>(null)

  useEffect(() => {
    setLines([])
    lastSeq.current = -1
  }, [runId])

  useEffect(() => {
    if (runId == null || !expanded) return
    let stopped = false
    let timer: number | undefined

    const tick = async () => {
      try {
        const batch = await getLogs(runId, lastSeq.current)
        if (stopped || batch.length === 0) return
        lastSeq.current = batch[batch.length - 1].seq
        setLines((prev) => [...prev, ...batch].slice(-MAX_LINES))
      } catch {
        /* transient errors are ignored; next tick retries */
      }
    }

    void tick()
    timer = window.setInterval(() => void tick(), active ? 1000 : 3000)
    return () => {
      stopped = true
      if (timer !== undefined) window.clearInterval(timer)
    }
  }, [runId, expanded, active])

  useEffect(() => {
    const node = preRef.current
    if (node) node.scrollTop = node.scrollHeight
  }, [lines])

  const text = lines.map((line) => line.line).join('\n')

  return (
    <Collapse
      activeKey={expanded ? ['logs'] : []}
      onChange={(keys) =>
        setExpanded(Array.isArray(keys) ? keys.includes('logs') : keys === 'logs')
      }
      items={[
        {
          key: 'logs',
          label: (
            <Typography.Text strong>
              原始日志<span style={{ color: '#889', fontWeight: 400 }}>（{lines.length} 行）</span>
            </Typography.Text>
          ),
          children: (
            <pre
              ref={preRef}
              className="mono"
              style={{
                margin: 0,
                padding: 14,
                background: '#0f1b2d',
                color: '#cfe0ff',
                borderRadius: 8,
                fontSize: 12,
                lineHeight: 1.55,
                maxHeight: 420,
                overflow: 'auto',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-all',
              }}
            >
              {text || (expanded ? '等待脚本输出…' : '')}
            </pre>
          ),
        },
      ]}
    />
  )
}