import { Table, Tag, Typography } from 'antd'
import type { TableProps } from 'antd'
import { roundStatusColor } from '../status'
import type { RoundRow } from '../types'

interface Props {
  rounds: RoundRow[]
}

const dash = (value: string | null | undefined) =>
  value && value.length > 0 ? value : '—'

export function RoundsTable({ rounds }: Props) {
  const statusFilters = Array.from(
    new Set(rounds.map((r) => r.status).filter((s): s is string => Boolean(s))),
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
      onFilter: (value, row) => row.status === value,
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
      scroll={{ x: 1080 }}
      locale={{ emptyText: '暂无轮次数据' }}
      expandable={{
        expandedRowRender: (row) => (
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
        ),
        rowExpandable: (row) => Boolean(row.log_excerpt),
      }}
    />
  )
}