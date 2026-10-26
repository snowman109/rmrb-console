import { useEffect, useState } from 'react'
import { Alert, Button, Form, Input, InputNumber, Select, Space } from 'antd'
import { listAvds } from '../api'
import type { Config } from '../types'

export interface NewRunValues {
  url: string
  rounds: number
  avd: string
}

interface Props {
  config: Config | null
  busy: boolean
  onSubmit: (values: NewRunValues) => Promise<void>
}

export function NewRunForm({ config, busy, onSubmit }: Props) {
  const [form] = Form.useForm<NewRunValues>()
  const [avds, setAvds] = useState<string[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    listAvds()
      .then((items) => {
        if (active) setAvds(items)
      })
      .catch(() => {
        if (active) setAvds([])
      })
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (!config) return
    form.setFieldsValue({
      url: config.default_url,
      rounds: config.default_rounds,
      avd: config.default_avd,
    })
  }, [config, form])

  const handleFinish = async (values: NewRunValues) => {
    setSubmitting(true)
    setError(null)
    try {
      await onSubmit(values)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSubmitting(false)
    }
  }

  const options = Array.from(
    new Set([...(config ? [config.default_avd] : []), ...avds]),
  )
    .filter(Boolean)
    .map((name) => ({ label: name, value: name }))

  return (
    <Form form={form} layout="vertical" onFinish={handleFinish} requiredMark={false}>
      <Form.Item
        name="url"
        label="推广链接"
        rules={[{ required: true, message: '请输入推广链接' }]}
      >
        <Input placeholder="https://…/?channelCode=…" allowClear />
      </Form.Item>

      <Space size={16} align="end" wrap>
        <Form.Item
          name="rounds"
          label="轮数"
          rules={[{ required: true, message: '请输入轮数' }]}
        >
          <InputNumber min={1} max={1000} style={{ width: 140 }} />
        </Form.Item>

        <Form.Item
          name="avd"
          label="模拟器 AVD"
          rules={[{ required: true, message: '请选择 AVD' }]}
        >
          <Select
            style={{ width: 240 }}
            options={options}
            showSearch
            placeholder="选择 AVD"
          />
        </Form.Item>

        <Form.Item>
          <Button type="primary" htmlType="submit" loading={submitting}>
            开始运行
          </Button>
        </Form.Item>
      </Space>

      {busy && (
        <Alert
          type="info"
          showIcon
          message="当前有运行在跑：新提交会排队，等当前运行结束后自动开始。"
        />
      )}

      {error && (
        <Alert style={{ marginTop: 12 }} type="error" showIcon message={error} />
      )}
    </Form>
  )
}