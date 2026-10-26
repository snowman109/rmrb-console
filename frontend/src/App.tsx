import { useCallback, useEffect, useState } from 'react'
import { Card, ConfigProvider, Layout, Space, Typography, message } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { cancelRun, createRun, getConfig, listRuns } from './api'
import { NewRunForm } from './components/NewRunForm'
import type { NewRunValues } from './components/NewRunForm'
import { RunOverview } from './components/RunOverview'
import { useRunPolling } from './hooks/useRunPolling'
import { palette, theme } from './theme'
import type { Config } from './types'

const { Sider, Content, Header } = Layout

export default function App() {
  const [config, setConfig] = useState<Config | null>(null)
  const [currentRunId, setCurrentRunId] = useState<number | null>(null)
  const { run, counts } = useRunPolling(currentRunId)
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

  const busy = run?.status === 'queued' || run?.status === 'running'

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
        <Sider width={280} style={{ padding: '22px 18px' }}>
          <Typography.Title level={4} style={{ color: '#fff', marginTop: 0 }}>
            AVD 归因控制台
          </Typography.Title>
          <Typography.Paragraph style={{ color: 'rgba(255,255,255,0.55)', fontSize: 13 }}>
            每轮重建模拟器 → 打开浏览器 → 下载安装 → 唤起 App，本地落库便于核对归因。
          </Typography.Paragraph>
          <Typography.Paragraph style={{ color: 'rgba(255,255,255,0.35)', fontSize: 12 }}>
            历史运行列表在下一步接入
          </Typography.Paragraph>
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
            </Space>
          </Content>
        </Layout>
      </Layout>
    </ConfigProvider>
  )
}