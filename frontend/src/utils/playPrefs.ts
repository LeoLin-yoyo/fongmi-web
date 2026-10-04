import { reactive, watch } from 'vue'

/** 播放打开方式偏好：点播/本地视频各自独立，是否在新浏览器标签页播放。
 *  纯浏览器侧行为偏好，存 localStorage（默认开 = 新标签页，保持历史行为）。 */
export type PlayOpenKind = 'vod' | 'local'

const STORAGE_KEY = 'fongmi_play_open_prefs'

export const playOpenPrefs = reactive<{ vod: boolean; local: boolean }>(load())

function load(): { vod: boolean; local: boolean } {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      return { vod: parsed.vod !== false, local: parsed.local !== false }
    }
  } catch {}
  return { vod: true, local: true }
}

watch(playOpenPrefs, (p) => {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(p)) } catch {}
})
