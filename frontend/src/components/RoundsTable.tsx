import { Table, Tag, Typography } from 'antd'
import type { TableProps } from 'antd'
import { roundStatusCode, roundStatusColor } from '../status'
import type { RoundRow, RunEvent } from '../types'

interface Props {
  rounds: RoundRow[]
  events: RunEvent[]
}

const dash = (value: string | null | undefined) =>
  value && value.length > 0 ? value : '—'

export function RoundsTable({ rounds, events }: Props) {
  const eventsByRound = new Map<number, RunEvent[]>()
  for (const event of events) {
    if (event.round_no == null) continue
    const bucket = eventsByRound.get(event.round_no) ?? []
    bucket.push(event)
    eventsByRound.set(event.round_no, bucket)
  }

  const statusFilters = Array.from(
    new Set(
      rounds.map((r) => roundStatusCode(r.status)).filter((s) => s.length > 0),
    ),
  )
    .sort()
    .map((status) => ({ text: status, value: status }))

  const columns: TableProps<RoundRow>['columns'] = [
    {
      title: '轮次',
      dataIndex: 'round_no',
      width: 80,
      sorter: (a, b) => a.round_no - b.round_no,
      defaultSortOrder: 'ascend',
    },
    {
      title: 'action',
      dataIndex: 'action',
      width: 90,
      render: dash,
    },
    {
      title: 'Android ID 前 → 后',
      key: 'android_id',
      render: (_, row) => (
        <Typography.Text className="mono" style={{ fontSize: 12 }}>
          {dash(row.android_id_before)} → {dash(row.android_id_after)}
        </Typography.Text>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 150,
      filters: statusFilters,
      onFilter: (value, row) => roundStatusCode(row.status) === value,
      sorter: (a, b) => (a.status ?? '').localeCompare(b.status ?? ''),
      render: (status: string | null) =>
        status ? <Tag color={roundStatusColor(status)}>{status}</Tag> : '—',
    },
    {
      title: 'channel',
      dataIndex: 'channel',
      width: 130,
      render: dash,
    },
    {
      title: 'public_ip',
      dataIndex: 'public_ip',
      width: 140,
      render: dash,
    },
    {
      title: 'installer',
      dataIndex: 'installer',
      width: 150,
      render: dash,
    },
    {
      title: 'apk_src',
      dataIndex: 'apk_src',
      width: 100,
      render: dash,
    },
    {
      title: '点击时间',
      dataIndex: 'clicked_at',
      width: 160,
      render: dash,
    },
    {
      title: '打开时间',
      dataIndex: 'open_at',
      width: 160,
      render: dash,
    },
  ]

  return (
    <Table<RoundRow>
      rowKey="round_no"
      size="middle"
      columns={columns}
      dataSource={rounds}
      pagination={false}
      scroll={{ x: 1360 }}
      locale={{ emptyText: '暂无轮次数据' }}
      expandable={{
        expandedRowRender: (row) => {
          const roundEvents = eventsByRound.get(row.round_no) ?? []
          return (
            <div style={{ display: 'grid', gap: 10 }}>
              <div>
                <Typography.Text strong style={{ fontSize: 12 }}>
                  本轮事件
                </Typography.Text>
                {roundEvents.length === 0 ? (
                  <Typography.Text type="secondary" style={{ marginLeft: 8 }}>
                    暂无事件
                  </Typography.Text>
                ) : (
                  <ul style={{ margin: '6px 0 0', paddingLeft: 18, fontSize: 12 }}>
                    {roundEvents.map((event) => (
                      <li key={event.id}>
                        <Typography.Text className="mono" style={{ fontSize: 12 }}>
                          {event.kind}
                        </Typography.Text>
                        <span style={{ color: '#556', marginLeft: 8 }}>
                          {event.message}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <pre
                className="mono"
                style={{
                  margin: 0,
                  whiteSpace: 'pre-wrap',
                  fontSize: 12,
                  color: '#334',
                  background: '#f7f9fd',
                  padding: 12,
                  borderRadius: 6,
                  maxHeight: 260,
                  overflow: 'auto',
                }}
              >
                {row.log_excerpt || '（无日志摘要）'}
              </pre>
            </div>
          )
        },
        rowExpandable: (row) =>
          Boolean(row.log_excerpt) || (eventsByRound.get(row.round_no)?.length ?? 0) > 0,
      }}
    />
  )
}