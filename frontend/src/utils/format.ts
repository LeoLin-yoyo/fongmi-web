export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || isNaN(seconds)) return '--:--'
  const s = Math.round(seconds)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
  return `${m}:${String(sec).padStart(2, '0')}`
}

export function formatSize(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return ''
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let v = bytes / 1024
  let i = 0
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++ }
  return `${v >= 100 ? v.toFixed(0) : v.toFixed(1)} ${units[i]}`
}

export function formatResolution(v: any): string {
  if (!v || !v.width || !v.height) return ''
  if (v.height >= 2160) return '4K'
  if (v.height >= 1080) return '1080P'
  if (v.height >= 720) return '720P'
  if (v.height >= 480) return '480P'
  return `${v.height}P`
}

export function formatCodec(codec: string): string {
  const map: Record<string, string> = {
    h264: 'H.264', hevc: 'H.265', vp9: 'VP9', av1: 'AV1',
    mpeg4: 'MPEG4', vp8: 'VP8', h263: 'H.263', wmv3: 'WMV3',
  }
  return map[codec] || (codec ? codec.toUpperCase() : '')
}
