import { useCallback, useEffect, useRef, useState } from 'react'
import { Card, ConfigProvider, Layout, Space, Typography, message } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { cancelRun, createRun, getConfig, getEvents, listRuns } from './api'
import { EventTimeline } from './components/EventTimeline'
import { HistorySidebar } from './components/HistorySidebar'
import { LogViewer } from './components/LogViewer'
import { NewRunForm } from './components/NewRunForm'
import type { NewRunValues } from './components/NewRunForm'
import { RoundsTable } from './components/RoundsTable'
import { RunOverview } from './components/RunOverview'
import { useRunPolling } from './hooks/useRunPolling'
import { TERMINAL_RUN_STATUSES } from './status'
import { palette, theme } from './theme'
import type { Config, RunEvent } from './types'

const { Sider, Content, Header } = Layout
const EVENT_POLL_MS = 2000
const MAX_EVENTS = 2000

export default function App() {
  const [config, setConfig] = useState<Config | null>(null)
  const [currentRunId, setCurrentRunId] = useState<number | null>(null)
  const [events, setEvents] = useState<RunEvent[]>([])
  const lastEventId = useRef(0)
  const { run, counts, rounds } = useRunPolling(currentRunId)
  const [messageApi, contextHolder] = message.useMessage()

  useEffect(() => {
    getConfig()
      .then(setConfig)
      .catch(() => setConfig(null))
    listRuns()
      .then((runs) => {
        if (runs.length > 0) setCurrentRunId((id) => id ?? runs[0].id)
      })
      .catch(() => undefined)
  }, [])

  useEffect(() => {
    setEvents([])
    lastEventId.current = 0
  }, [currentRunId])

  const runStatus = run?.status
  useEffect(() => {
    if (currentRunId == null) return
    let stopped = false
    let timer: number | undefined

    const tick = async () => {
      try {
        const batch = await getEvents(currentRunId, lastEventId.current)
        if (stopped || batch.length === 0) return
        lastEventId.current = batch[batch.length - 1].id
        setEvents((prev) => [...prev, ...batch].slice(-MAX_EVENTS))
      } catch {
        /* transient errors are ignored; next tick retries */
      }
    }

    void tick()
    if (!runStatus || !TERMINAL_RUN_STATUSES.has(runStatus)) {
      timer = window.setInterval(() => void tick(), EVENT_POLL_MS)
    }
    return () => {
      stopped = true
      if (timer !== undefined) window.clearInterval(timer)
    }
  }, [currentRunId, runStatus])

  const busy = runStatus === 'queued' || runStatus === 'running'

  const handleSubmit = useCallback(
    async (values: NewRunValues) => {
      const { id } = await createRun(values)
      setCurrentRunId(id)
      messageApi.success(`已提交运行 #${id}`)
    },
    [messageApi],
  )

  const handleCancel = useCallback(async () => {
    if (currentRunId == null) return
    try {
      const { canceled } = await cancelRun(currentRunId)
      if (canceled) {
        messageApi.warning('取消信号已发送，正在收尾')
      } else {
        messageApi.info('该运行当前不在执行中')
      }
    } catch (err) {
      messageApi.error(err instanceof Error ? err.message : String(err))
    }
  }, [currentRunId, messageApi])

  return (
    <ConfigProvider locale={zhCN} theme={theme}>
      {contextHolder}
      <Layout style={{ minHeight: '100vh' }}>
        <Sider
          width={290}
          style={{ padding: '22px 16px', overflow: 'auto', height: '100vh', position: 'sticky', top: 0 }}
        >
          <Typography.Title level={4} style={{ color: '#fff', marginTop: 0, marginBottom: 6 }}>
            AVD 归因控制台
          </Typography.Title>
          <Typography.Paragraph
            style={{ color: 'rgba(255,255,255,0.5)', fontSize: 12, marginBottom: 20 }}
          >
            每轮重建模拟器 → 浏览器下载 → 安装 → 唤起 App
          </Typography.Paragraph>
          <HistorySidebar selectedId={currentRunId} onSelect={setCurrentRunId} />
        </Sider>

        <Layout>
          <Header
            style={{
              display: 'flex',
              alignItems: 'center',
              padding: '0 24px',
              borderBottom: `1px solid ${palette.canvas}`,
            }}
          >
            <Typography.Text strong style={{ fontSize: 16 }}>
              本地测试控制台
            </Typography.Text>
          </Header>

          <Content style={{ padding: 24 }}>
            <Space direction="vertical" size={20} style={{ width: '100%' }}>
              <Card title="新建运行">
                <NewRunForm config={config} busy={busy} onSubmit={handleSubmit} />
              </Card>

              <Card title="运行概览">
                <RunOverview run={run} counts={counts} onCancel={handleCancel} />
              </Card>

              <Card title="轮次明细">
                <RoundsTable rounds={rounds} events={events} />
              </Card>

              <Card title="事件时间线">
                <EventTimeline events={events} />
              </Card>

              <Card title="原始日志">
                <LogViewer runId={currentRunId} active={busy} />
              </Card>
            </Space>
          </Content>
        </Layout>
      </Layout>
    </ConfigProvider>
  )
}