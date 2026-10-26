import { Card, ConfigProvider, Empty, Layout, Typography } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { theme } from './theme'

const { Sider, Content, Header } = Layout

export default function App() {
  return (
    <ConfigProvider locale={zhCN} theme={theme}>
      <Layout style={{ minHeight: '100vh' }}>
        <Sider width={280} style={{ padding: '20px 16px' }}>
          <Typography.Title level={4} style={{ color: '#fff', marginTop: 0 }}>
            AVD 归因控制台
          </Typography.Title>
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={<span style={{ color: 'rgba(255,255,255,0.45)' }}>历史运行</span>}
          />
        </Sider>
        <Layout>
          <Header style={{ display: 'flex', alignItems: 'center', padding: '0 24px' }}>
            <Typography.Text strong style={{ fontSize: 16 }}>
              手机归因测试 · 本地控制台
            </Typography.Text>
          </Header>
          <Content style={{ padding: 24 }}>
            <Card title="当前运行">
              <Empty description="还没有正在进行的运行" />
            </Card>
          </Content>
        </Layout>
      </Layout>
    </ConfigProvider>
  )
}