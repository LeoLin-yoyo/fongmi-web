<template>
  <div class="settings-page">
    <BackTop />
    <div class="page-header">
      <h2>
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:-4px;margin-right:6px">
          <circle cx="12" cy="12" r="3"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>
        </svg>
        设置
      </h2>
    </div>

    <nav class="anchor-bar" aria-label="设置项快速定位">
      <button
        v-for="s in sections"
        :key="s.key"
        class="anchor-chip"
        :class="{ active: activeSection === s.key }"
        @click="scrollToSection(s.key)"
      >
        {{ s.label }}
      </button>
    </nav>

    <div class="section" id="sec-subscribe">
      <n-card title="订阅管理">
        <n-tabs type="line" animated>
          <n-tab-pane name="url" tab="点播源导入">
            <n-space vertical :size="12">
              <n-input v-model:value="url" type="textarea" placeholder="请输入订阅URL（每行一个，支持批量导入）" :autosize="{ minRows: 3, maxRows: 8 }" />
              <div class="btn-row">
                <n-button :loading="checking" @click="checkUrls">检测可用性</n-button>
                <n-button type="primary" :loading="importing" @click="importUrl">导入</n-button>
              </div>
              <div v-if="checkResults.length" class="check-results">
                <div v-for="r in checkResults" :key="r.url" class="check-item" :class="{ ok: r.available, fail: !r.available }">
                  <span class="check-icon">{{ r.available ? '✓' : '✗' }}</span>
                  <span class="check-url" :title="r.url">{{ shortUrl(r.url) }}</span>
                  <span class="check-detail">{{ r.detail }}</span>
                  <span v-if="r.site_count" class="check-count">{{ r.site_count }}站点</span>
                </div>
              </div>
            </n-space>
          </n-tab-pane>
          <n-tab-pane name="live" tab="直播源导入">
            <n-space vertical :size="12">
              <n-input v-model:value="liveUrl" type="textarea" placeholder="请输入直播源URL（m3u/txt，每行一个）" :autosize="{ minRows: 3, maxRows: 8 }" />
              <div class="btn-row">
                <n-button :loading="liveChecking" @click="checkLiveUrls">检测</n-button>
                <n-button type="primary" :loading="liveImporting" @click="importLiveUrls">导入直播源</n-button>
              </div>
              <div v-if="liveCheckResults.length" class="check-results">
                <div v-for="r in liveCheckResults" :key="r.url" class="check-item" :class="{ ok: r.available, fail: !r.available }">
                  <span class="check-icon">{{ r.available ? '✓' : '✗' }}</span>
                  <span class="check-url" :title="r.url">{{ shortUrl(r.url) }}</span>
                  <span class="check-detail">{{ r.detail }}</span>
                </div>
              </div>
            </n-space>
          </n-tab-pane>
          <n-tab-pane name="file" tab="文件上传">
            <n-upload :custom-request="onUpload" :show-file-list="false" accept=".json">
              <n-upload-dragger>
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="opacity:0.3">
                  <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
                </svg>
                <n-text style="font-size:16px">点击或拖拽 JSON 配置文件到此处</n-text>
              </n-upload-dragger>
            </n-upload>
          </n-tab-pane>
        </n-tabs>
      </n-card>
    </div>

    <div class="section" id="sec-configs">
      <n-card>
        <template #header>
          <div class="card-head">
            <span>点播配置列表</span>
            <n-button size="tiny" quaternary @click="toggleCollapse('configs')">
              {{ collapsed.configs ? `展开（${configs.length}）` : '收起' }}
            </n-button>
          </div>
        </template>
        <div v-show="!collapsed.configs">
          <div v-if="!configs.length" class="no-config">暂无配置</div>
          <div v-for="cfg in configs" :key="cfg.id" class="config-item">
            <div class="config-info">
              <span class="config-name">{{ cfg.name || '未命名配置' }}</span>
              <n-tag v-if="cfg.enabled" size="small" type="success">已启用</n-tag>
              <n-tag v-else size="small">已禁用</n-tag>
              <span class="config-meta">{{ cfg.type === 'live' ? '直播' : '点播' }}</span>
              <span v-if="cfg.url" class="config-url" :title="cfg.url">{{ cfg.url }}</span>
            </div>
            <div class="config-actions">
              <n-switch :value="!!cfg.enabled" @update:value="() => toggle(cfg.id)" />
              <n-button size="small" ghost @click="startRename(cfg)">重命名</n-button>
              <n-button size="small" type="error" ghost @click="remove(cfg.id)">删除</n-button>
            </div>
          </div>
        </div>
      </n-card>
    </div>

    <div class="section" id="sec-livesrc">
      <n-card title="直接导入的直播源">
        <div v-if="!liveSources.length" class="no-config">暂无直接导入的直播源</div>
        <div v-for="src in liveSources" :key="src.id" class="config-item">
          <div class="config-info">
            <span class="config-name">{{ src.name }}</span>
            <n-tag size="small" type="info">{{ src.type }}</n-tag>
            <span class="config-meta">{{ src.group_count }}组 {{ src.channel_count }}频道</span>
          </div>
          <div class="config-actions">
            <n-switch :value="!!src.enabled" @update:value="() => toggleLive(src.id)" />
            <n-button size="small" type="error" ghost @click="removeLive(src.id)">删除</n-button>
          </div>
        </div>
      </n-card>
    </div>

    <div class="section" id="sec-proxy">
      <n-card title="代理设置">
        <n-space vertical :size="12">
          <n-input v-model:value="proxy" placeholder="http://127.0.0.1:7890 （留空则自动尝试系统代理）" />
          <n-button type="primary" @click="saveProxy">保存</n-button>
          <p class="hint">优先级：此处配置 → 环境变量 → Windows 系统代理 → 直连。用于直播源下载、远程站点访问和封面图片代理。</p>
        </n-space>
      </n-card>
    </div>

    <div class="section" id="sec-play">
      <n-card title="播放设置">
        <div class="pref-item">
          <div class="pref-info">
            <div class="pref-name">点播视频：新标签页播放</div>
            <div class="pref-desc">开启后点击点播视频在浏览器新标签页打开；关闭则在当前页跳转</div>
          </div>
          <n-switch v-model:value="playOpenPrefs.vod" />
        </div>
        <div class="pref-item">
          <div class="pref-info">
            <div class="pref-name">本地视频：新标签页播放</div>
            <div class="pref-desc">开启后点击本地视频在浏览器新标签页播放；关闭则在当前页跳转。两项配置互相独立</div>
          </div>
          <n-switch v-model:value="playOpenPrefs.local" />
        </div>
      </n-card>
    </div>

    <div class="section" id="sec-local">
      <n-card>
        <template #header>
          <div class="card-head">
            <span>本地视频</span>
            <n-button size="tiny" quaternary @click="toggleCollapse('local')">
              {{ collapsed.local ? `展开（${dirs.length} 目录）` : '收起' }}
            </n-button>
          </div>
        </template>
        <div v-show="!collapsed.local">
        <div class="stats-row">
          <div class="stat-card">
            <div class="num">{{ stats.video_count ?? '–' }}</div>
            <div class="label">视频总数</div>
          </div>
          <div class="stat-card">
            <div class="num">{{ stats.dir_count ?? '–' }}</div>
            <div class="label">媒体目录</div>
          </div>
          <div class="stat-card">
            <div class="num">{{ formatSize(stats.total_size) }}</div>
            <div class="label">总容量</div>
          </div>
        </div>
        <n-space vertical :size="12">
          <div class="ext-player-section">
            <div class="group-title">外部播放器<span class="group-hint">本机播放器程序完整路径（如 PotPlayer），用于片库页视频卡片角标一键调用</span></div>
            <div class="dir-form">
              <n-input v-model:value="externalPlayer" placeholder="例如：D:\Program Files\DAUM\PotPlayer\PotPlayerMini64.exe" @keyup.enter="saveExternalPlayer" clearable />
              <n-button type="primary" :loading="savingPlayer" @click="saveExternalPlayer">保存</n-button>
            </div>
            <p class="hint">路径持久化保存，应用重启不丢失；留空则片库页不显示外部播放按钮。调用入口仅桌面端浏览器显示（移动终端无法调起本机播放器）。</p>
          </div>
          <div class="dir-form">
            <n-input v-model:value="newDir" placeholder="例如：F:\telegram" @keyup.enter="addDir" />
            <n-button type="primary" :loading="adding" :disabled="!newDir.trim()" @click="addDir">添加目录</n-button>
          </div>
          <div v-if="!dirs.length" class="no-config">尚未添加任何目录</div>
          <div v-for="(d, idx) in dirs" :key="d.id" class="dir-item" :class="{ 'dir-hidden': !isDirVisible(d) }">
            <div class="dir-info">
              <div class="dir-path" :title="d.path">{{ d.path }}</div>
              <div class="dir-meta">
                <span>{{ d.video_count }} 个视频</span>
                <span v-if="d.last_scan">上次扫描：{{ d.last_scan }}</span>
                <span v-else>尚未扫描</span>
                <span v-if="!isDirVisible(d)" class="dir-off-tag">片库页隐藏</span>
              </div>
            </div>
            <div class="dir-actions">
              <n-switch
                size="small"
                :value="isDirVisible(d)"
                :loading="visibilitySaving.has(d.id)"
                @update:value="(v: boolean) => toggleDirVisible(d, v)"
              >
                <template #checked>显示</template>
                <template #unchecked>隐藏</template>
              </n-switch>
              <n-button size="small" quaternary circle :disabled="idx === 0" title="上移" aria-label="上移" @click="moveDir(idx, -1)">↑</n-button>
              <n-button size="small" quaternary circle :disabled="idx === dirs.length - 1" title="下移" aria-label="下移" @click="moveDir(idx, 1)">↓</n-button>
              <n-button size="small" :loading="scanning" @click="scanDir(d)">扫描</n-button>
              <n-button size="small" type="error" ghost @click="removeDir(d)">删除</n-button>
            </div>
          </div>
          <p v-if="dirs.length > 1" class="hint">用 ↑↓ 调整目录顺序；「隐藏」的目录不在片库页选项卡中显示，但仍会扫描并参与聚合选项卡。</p>
          <div class="group-section">
            <div class="group-title">聚合选项卡<span class="group-hint">把多个目录合并成一个选项卡在片库页展示（至少选 2 个目录）</span></div>
            <div class="group-form">
              <n-input v-model:value="groupName" placeholder="聚合选项卡名称，例如：电影" @keyup.enter="saveGroup" />
              <n-select v-model:value="groupDirIds" multiple clearable :options="dirOptions" placeholder="选择要合并的目录（至少 2 个）" />
              <div class="group-actions">
                <n-button type="primary" size="small" :disabled="!canSaveGroup" :loading="savingGroup" @click="saveGroup">
                  {{ editingGroupId ? '保存修改' : '创建聚合选项卡' }}
                </n-button>
                <n-button v-if="editingGroupId" size="small" @click="cancelEditGroup">取消</n-button>
              </div>
            </div>
            <div v-if="!groups.length" class="no-group">尚未创建聚合选项卡</div>
            <div v-for="g in groups" :key="g.id" class="group-item">
              <div class="dir-info">
                <div class="dir-path" :title="groupDirsLabel(g)">{{ g.name }}</div>
                <div class="dir-meta">{{ groupDirsLabel(g) }}</div>
              </div>
              <div class="dir-actions">
                <n-button size="small" @click="startEditGroup(g)">编辑</n-button>
                <n-button size="small" type="error" ghost @click="removeGroup(g)">删除</n-button>
              </div>
            </div>
          </div>
        </n-space>
        </div>
      </n-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, onMounted, onUnmounted, nextTick } from 'vue'
import { useMessage, NCard, NTabs, NTabPane, NInput, NButton, NUpload, NUploadDragger, NText, NTag, NSpace, NSwitch, NSelect } from 'naive-ui'
import { importConfig, importBatch, getConfigs, deleteConfig, toggleConfig, checkBatch, importLiveBatch, getLiveSources, deleteLiveSource, toggleLiveSource, renameConfig } from '@/api/config'
import { localAPI } from '@/api/local'
import { playOpenPrefs } from '@/utils/playPrefs'
import BackTop from '@/components/BackTop.vue'

const message = useMessage()
const url = ref('')
const importing = ref(false)
const checking = ref(false)
const checkResults = ref<any[]>([])
const configs = ref<any[]>([])
const liveUrl = ref('')
const liveImporting = ref(false)
const liveChecking = ref(false)
const liveCheckResults = ref<any[]>([])
const liveSources = ref<any[]>([])
const proxy = ref('')
const externalPlayer = ref('')
const savingPlayer = ref(false)
const dirs = ref<any[]>([])
const stats = ref<any>({})
const newDir = ref('')
const adding = ref(false)
const scanning = ref(false)
const groups = ref<any[]>([])
const groupName = ref('')
const groupDirIds = ref<number[]>([])
const editingGroupId = ref<number | null>(null)
const savingGroup = ref(false)
const visibilitySaving = reactive(new Set<number>())
let pollTimer: number | undefined

const dirOptions = computed(() => dirs.value.map(d => ({ label: d.path, value: d.id })))
const canSaveGroup = computed(() => !!groupName.value.trim() && groupDirIds.value.length >= 2)

// ── 锚点菜单 ──
const sections = [
  { key: 'sec-subscribe', label: '订阅管理' },
  { key: 'sec-configs', label: '点播配置' },
  { key: 'sec-livesrc', label: '直播源' },
  { key: 'sec-proxy', label: '代理设置' },
  { key: 'sec-play', label: '播放设置' },
  { key: 'sec-local', label: '本地视频' },
]
const activeSection = ref('sec-subscribe')
/** App 外层 n-layout 的滚动容器；不能用 window，也不用内层 .n-layout-scroll-container */
function scrollContainer() {
  return document.querySelector<HTMLElement>('.n-layout--absolute-positioned > .n-layout-scroll-container')
}

function scrollToSection(key: string) {
  const el = document.getElementById(key)
  const container = scrollContainer()
  if (!el || !container) return
  activeSection.value = key
  // 减去吸顶头部（56px）+ 锚点条高度，避免目标被遮住
  const top = el.offsetTop - container.offsetTop - 106
  container.scrollTo({ top: Math.max(0, top), behavior: 'smooth' })
}

let spyRaf = 0
function onScrollSpy() {
  if (spyRaf) return
  spyRaf = window.requestAnimationFrame(() => {
    spyRaf = 0
    const container = scrollContainer()
    if (!container) return
    const pos = container.scrollTop + 140
    let current = sections[0].key
    for (const s of sections) {
      const el = document.getElementById(s.key)
      if (el && el.offsetTop - container.offsetTop <= pos) current = s.key
    }
    activeSection.value = current
  })
}

// ── 卡片折叠（状态持久化，长列表默认收起以内缩短滚动距离）──
const COLLAPSE_KEY = 'fongmi_setting_collapse'
const collapsed = ref<Record<string, boolean>>(loadCollapse())

function loadCollapse(): Record<string, boolean> {
  try {
    const raw = localStorage.getItem(COLLAPSE_KEY)
    if (raw) return { configs: true, local: true, ...JSON.parse(raw) }
  } catch {}
  return { configs: true, local: true }
}

function toggleCollapse(key: string) {
  collapsed.value = { ...collapsed.value, [key]: !collapsed.value[key] }
  try { localStorage.setItem(COLLAPSE_KEY, JSON.stringify(collapsed.value)) } catch {}
}

function formatSize(bytes: number) {
  if (bytes === null || bytes === undefined) return '–'
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let v = bytes / 1024
  let i = 0
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++ }
  return `${v >= 100 ? v.toFixed(0) : v.toFixed(1)} ${units[i]}`
}

function shortUrl(u: string) {
  if (u.length <= 50) return u
  return u.substring(0, 47) + '...'
}

async function refreshLocal() {
  dirs.value = await localAPI.dirs().catch(() => [])
  stats.value = await localAPI.stats().catch(() => ({}))
}

function isDirVisible(d: any) {
  return d.visible === undefined ? true : !!d.visible
}

async function toggleDirVisible(d: any, visible: boolean) {
  visibilitySaving.add(d.id)
  const prev = d.visible
  d.visible = visible ? 1 : 0
  try {
    await localAPI.setDirVisible(d.id, visible)
  } catch (e: any) {
    d.visible = prev
    message.error(`设置失败：${e?.response?.data?.detail || e.message}`)
  } finally {
    visibilitySaving.delete(d.id)
  }
}

async function addDir() {
  const path = newDir.value.trim()
  if (!path) return
  adding.value = true
  try {
    await localAPI.addDir(path)
    message.success('添加成功')
    newDir.value = ''
    await refreshLocal()
    localAPI.scanAll().catch(() => {})
  } catch (e: any) {
    message.error(`添加失败：${e.message}`)
  } finally {
    adding.value = false
  }
}

async function removeDir(d: any) {
  if (!confirm(`确定移除目录「${d.path}」？`)) return
  try {
    await localAPI.deleteDir(d.id)
    message.success('已移除')
    await refreshLocal()
  } catch (e: any) {
    message.error(`删除失败：${e.message}`)
  }
}

async function moveDir(idx: number, delta: number) {
  const target = idx + delta
  if (target < 0 || target >= dirs.value.length) return
  const prev = dirs.value
  const list = [...prev]
  ;[list[idx], list[target]] = [list[target], list[idx]]
  dirs.value = list
  try {
    await localAPI.reorderDirs(list.map(d => d.id))
  } catch (e: any) {
    dirs.value = prev
    message.error(`排序失败：${e.message}`)
  }
}

async function refreshGroups() {
  groups.value = await localAPI.groups().catch(() => groups.value)
}

function groupDirsLabel(g: any) {
  return (g.dir_ids || []).map((id: number) => dirs.value.find(d => d.id === id)?.path || `#${id}`).join(' + ')
}

function startEditGroup(g: any) {
  editingGroupId.value = g.id
  groupName.value = g.name
  groupDirIds.value = [...g.dir_ids]
}

function cancelEditGroup() {
  editingGroupId.value = null
  groupName.value = ''
  groupDirIds.value = []
}

async function saveGroup() {
  if (!canSaveGroup.value) return
  savingGroup.value = true
  try {
    if (editingGroupId.value) {
      await localAPI.updateGroup(editingGroupId.value, groupName.value.trim(), [...groupDirIds.value])
      message.success('聚合选项卡已保存')
    } else {
      await localAPI.createGroup(groupName.value.trim(), [...groupDirIds.value])
      message.success('聚合选项卡已创建')
    }
    cancelEditGroup()
    await refreshGroups()
  } catch (e: any) {
    message.error(`保存失败：${e?.response?.data?.detail || e.message}`)
  } finally {
    savingGroup.value = false
  }
}

async function removeGroup(g: any) {
  if (!confirm(`删除聚合选项卡「${g.name}」？（不影响目录和视频）`)) return
  if (editingGroupId.value === g.id) cancelEditGroup()
  try {
    await localAPI.deleteGroup(g.id)
    message.success('已删除')
    await refreshGroups()
  } catch (e: any) {
    message.error(`删除失败：${e.message}`)
  }
}

async function scanDir(d: any) {
  try {
    await localAPI.scanDir(d.id)
    message.success('扫描已开始')
  } catch (e: any) {
    message.error(`扫描失败：${e.message}`)
  }
}

async function pollLocalStatus() {
  const s = await localAPI.scanStatus().catch(() => ({ scanning: false }))
  scanning.value = s.scanning
}

onMounted(async () => {
  try {
    const res = await fetch('/api/system/config')
    const data = await res.json()
    proxy.value = data?.data?.proxy || ''
    externalPlayer.value = data?.data?.external_player_path || ''
  } catch {}
  await loadConfigs()
  await loadLiveSources()
  await refreshLocal()
  refreshGroups()
  pollLocalStatus()
  pollTimer = window.setInterval(async () => {
    await pollLocalStatus()
    if (scanning.value) refreshLocal()
  }, 2000)
  await nextTick()
  scrollContainer()?.addEventListener('scroll', onScrollSpy, { passive: true })
  onScrollSpy()
})

onUnmounted(() => {
  clearInterval(pollTimer)
  scrollContainer()?.removeEventListener('scroll', onScrollSpy)
  if (spyRaf) cancelAnimationFrame(spyRaf)
})

async function saveProxy() {
  try {
    await fetch('/api/system/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ proxy: proxy.value.trim() }),
    })
    message.success('保存成功，请刷新页面生效')
  } catch (e: any) {
    message.error('保存失败: ' + (e?.message || ''))
  }
}

async function saveExternalPlayer() {
  savingPlayer.value = true
  try {
    const res = await fetch('/api/system/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ external_player_path: externalPlayer.value.trim() }),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    message.success('外部播放器路径已保存')
  } catch (e: any) {
    message.error('保存失败: ' + (e?.message || ''))
  } finally {
    savingPlayer.value = false
  }
}

async function loadConfigs() {
  const res: any = await getConfigs()
  configs.value = res.data || []
}

async function loadLiveSources() {
  const res: any = await getLiveSources()
  liveSources.value = res.data || []
}

async function checkUrls() {
  if (!url.value.trim()) return
  checking.value = true
  checkResults.value = []
  try {
    const urls = url.value.split('\n').map(u => u.trim()).filter(Boolean)
    const res: any = await checkBatch(urls)
    checkResults.value = res.results || []
    const ok = checkResults.value.filter(r => r.available).length
    message.success(`检测完成: ${ok}/${urls.length} 可用`)
  } catch (e: any) {
    message.error('检测失败')
  } finally {
    checking.value = false
  }
}

async function importUrl() {
  if (!url.value.trim()) return message.warning('请输入URL')
  importing.value = true
  try {
    const urls = url.value.split('\n').map(u => u.trim()).filter(Boolean)
    if (urls.length === 1) {
      await importConfig({ url: urls[0], type: 'url' })
      message.success('导入成功')
    } else {
      const res: any = await importBatch(urls)
      const success = res.results?.filter((r: any) => r.status === 'success').length || 0
      const errors = res.results?.filter((r: any) => r.status === 'error').length || 0
      const skipped = res.results?.filter((r: any) => r.status === 'skipped').length || 0
      message.success(`导入完成: ${success} 成功, ${skipped} 跳过, ${errors} 失败`)
    }
    url.value = ''
    checkResults.value = []
    await loadConfigs()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '导入失败')
  } finally {
    importing.value = false
  }
}

async function checkLiveUrls() {
  if (!liveUrl.value.trim()) return
  liveChecking.value = true
  liveCheckResults.value = []
  try {
    const urls = liveUrl.value.split('\n').map(u => u.trim()).filter(Boolean)
    const res: any = await checkBatch(urls)
    liveCheckResults.value = res.results || []
    const ok = liveCheckResults.value.filter(r => r.available).length
    message.success(`检测完成: ${ok}/${urls.length} 可用`)
  } catch (e: any) {
    message.error('检测失败')
  } finally {
    liveChecking.value = false
  }
}

async function importLiveUrls() {
  if (!liveUrl.value.trim()) return message.warning('请输入直播源URL')
  liveImporting.value = true
  try {
    const urls = liveUrl.value.split('\n').map(u => u.trim()).filter(Boolean)
    const items = urls.map(u => ({ url: u, name: '' }))
    const res: any = await importLiveBatch(items)
    const success = res.results?.filter((r: any) => r.status === 'success').length || 0
    const skipped = res.results?.filter((r: any) => r.status === 'skipped').length || 0
    message.success(`导入完成: ${success} 成功, ${skipped} 跳过`)
    liveUrl.value = ''
    liveCheckResults.value = []
    await loadLiveSources()
  } catch (e: any) {
    message.error('导入失败')
  } finally {
    liveImporting.value = false
  }
}

async function onUpload(options: any) {
  const file = options.file.file as File
  if (!file) return
  const reader = new FileReader()
  reader.onload = async (e) => {
    try {
      await importConfig({ content: e.target?.result as string, type: 'file' })
      message.success('上传成功')
      await loadConfigs()
      options.onFinish()
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '上传失败')
      options.onError()
    }
  }
  reader.readAsText(file)
}

async function toggle(id: number) {
  await toggleConfig(id)
  await loadConfigs()
}

async function remove(id: number) {
  await deleteConfig(id)
  await loadConfigs()
}

function startRename(cfg: any) {
  const input = window.prompt('重命名配置', cfg.name || '')
  if (input === null) return
  const name = input.trim()
  if (!name) {
    message.warning('名称不能为空')
    return
  }
  if (name === cfg.name) return
  renameConfig(cfg.id, name)
    .then(() => loadConfigs())
    .catch(() => message.error('重命名失败'))
}

async function toggleLive(id: number) {
  await toggleLiveSource(id)
  await loadLiveSources()
}

async function removeLive(id: number) {
  await deleteLiveSource(id)
  await loadLiveSources()
}
</script>

<style scoped>
.settings-page { padding: 20px; max-width: 800px; margin: 0 auto; }
.page-header h2 { margin: 0 0 12px; }
/* 锚点条：吸顶在 App 头部(56px)之下，横向滚动避免窄屏挤压 */
.anchor-bar {
  position: sticky; top: 56px; z-index: 10;
  display: flex; gap: 8px; overflow-x: auto; padding: 8px 0 10px;
  margin-bottom: 14px; background: var(--bg-color);
  border-bottom: 1px solid var(--n-border-color);
  scrollbar-width: none;
}
.anchor-bar::-webkit-scrollbar { display: none; }
.anchor-chip {
  flex-shrink: 0; padding: 5px 14px; border-radius: 16px; cursor: pointer;
  border: 1px solid var(--n-border-color); background: var(--n-base-color);
  color: #888; font-size: 13px; transition: all 0.2s; white-space: nowrap;
}
.anchor-chip:hover { color: var(--n-text-color); border-color: var(--n-primary-color); }
.anchor-chip.active { background: var(--n-primary-color); border-color: var(--n-primary-color); color: #fff; font-weight: 600; }
.card-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.section { margin-bottom: 20px; scroll-margin-top: 106px; }
.btn-row { display: flex; gap: 10px; }
.check-results { max-height: 300px; overflow-y: auto; border: 1px solid var(--n-border-color); border-radius: 8px; padding: 8px; }
.check-item { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border-radius: 4px; font-size: 12px; }
.check-item.ok { color: #52c41a; }
.check-item.fail { color: #ff4d4f; }
.check-icon { font-weight: bold; flex-shrink: 0; width: 16px; text-align: center; }
.check-url { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--n-text-color); }
.check-detail { color: #888; flex-shrink: 0; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.check-count { color: #888; flex-shrink: 0; }
.config-item { display: flex; align-items: center; gap: 8px; padding: 12px 0; border-bottom: 1px solid var(--n-divider-color); }
.config-item:last-child { border-bottom: none; }
.config-info { flex: 1; display: flex; align-items: center; gap: 8px; min-width: 0; }
.config-name { font-size: 14px; font-weight: 500; flex-shrink: 0; }
.config-meta { font-size: 11px; color: #888; background: var(--n-divider-color); padding: 1px 6px; border-radius: 3px; flex-shrink: 0; }
.config-url { font-size: 11px; color: #666; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 320px; }
.config-actions { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.hint { font-size: 12px; color: #888; margin: 0; }
.stats-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 16px; }
.stat-card { background: var(--n-base-color); border: 1px solid var(--n-border-color); border-radius: 10px; padding: 14px; }
.stat-card .num { font-size: 24px; font-weight: 700; }
.stat-card .label { font-size: 12px; color: #888; margin-top: 4px; }
.dir-form { display: flex; gap: 10px; }
.dir-item, .group-item { display: flex; align-items: center; gap: 12px; padding: 12px; background: var(--n-base-color); border: 1px solid var(--n-border-color); border-radius: 10px; }
.dir-info { flex: 1; min-width: 0; }
.dir-path { font-weight: 600; font-size: 14px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dir-meta { font-size: 12px; color: #888; margin-top: 4px; display: flex; gap: 10px; flex-wrap: wrap; }
.dir-actions { display: flex; gap: 8px; flex-shrink: 0; align-items: center; }
.dir-hidden .dir-path { opacity: 0.55; }
.dir-off-tag { color: #e6a23c; }
.group-section { margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--n-divider-color); }
/* 外部播放器区块与聚合区共用视觉，但用独立类名，避免 e2e 的 .group-section 选择器串味 */
.ext-player-section { margin-top: 16px; }
.group-title { font-weight: 600; font-size: 14px; margin-bottom: 10px; }
.group-hint { font-size: 12px; color: #888; font-weight: 400; margin-left: 8px; }
.group-form { display: flex; flex-direction: column; gap: 8px; }
.group-actions { display: flex; gap: 8px; }
.no-group { text-align: center; padding: 16px; color: #888; font-size: 13px; }
.pref-item { display: flex; align-items: center; gap: 16px; padding: 12px 0; border-bottom: 1px solid var(--n-divider-color); }
.pref-item:last-child { border-bottom: none; }
.pref-info { flex: 1; min-width: 0; }
.pref-name { font-size: 14px; font-weight: 500; }
.pref-desc { font-size: 12px; color: #888; margin-top: 4px; }
.no-config { text-align: center; padding: 24px; color: #888; font-size: 14px; }
@media (max-width: 640px) {
  .stats-row { grid-template-columns: repeat(3, 1fr); gap: 8px; }
  .stat-card { padding: 10px; }
  .stat-card .num { font-size: 18px; }
}
</style>