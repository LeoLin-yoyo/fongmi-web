/**
 * 埋点基线上报（T0-1）— fire-and-forget，失败静默
 * 事件类型：ttff / session / complete / nav / error
 */

function getSessionId(): string {
  try {
    let sid = sessionStorage.getItem('fongmi_metric_sid')
    if (!sid) {
      sid = `s_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
      sessionStorage.setItem('fongmi_metric_sid', sid)
    }
    return sid
  } catch {
    return `s_${Date.now()}`
  }
}

export function track(type: string, data: Record<string, unknown> = {}): void {
  try {
    const body = JSON.stringify({ type, sid: getSessionId(), ts: Date.now(), data })
    fetch('/api/metrics/event', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
      keepalive: true,
    }).catch(() => {})
  } catch {
    /* 埋点不干扰主流程 */
  }
}

/** 页面跳转上报：用于统计首页→首次播放步数 */
export function trackNav(from: string, to: string): void {
  track('nav', { from, to })
}
