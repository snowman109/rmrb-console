import type { ThemeConfig } from 'antd'

export const palette = {
  primary: '#2f6fed',
  success: '#1f9d55',
  warning: '#d9822b',
  danger: '#d64545',
  ink: '#16233a',
  muted: '#6b7a90',
  surface: '#ffffff',
  canvas: '#f4f6fb',
  sider: '#101c30',
}

export const theme: ThemeConfig = {
  token: {
    colorPrimary: palette.primary,
    colorSuccess: palette.success,
    colorWarning: palette.warning,
    colorError: palette.danger,
    colorTextBase: palette.ink,
    colorBgLayout: palette.canvas,
    borderRadius: 8,
    fontSize: 14,
    fontFamily:
      "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif",
  },
  components: {
    Layout: {
      siderBg: palette.sider,
      headerBg: palette.surface,
      bodyBg: palette.canvas,
    },
    Menu: {
      darkItemBg: palette.sider,
      darkItemSelectedBg: '#1d2f4d',
    },
    Card: {
      headerFontSize: 15,
      paddingLG: 20,
    },
    Table: {
      headerBg: '#f7f9fd',
      headerColor: palette.muted,
      rowHoverBg: '#f5f8ff',
    },
    Statistic: {
      contentFontSize: 22,
    },
  },
}