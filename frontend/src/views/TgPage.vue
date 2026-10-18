<template>
  <div class="tg-page">
    <BackTop />
    <div class="page-header">
      <h2>
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:-4px;margin-right:6px">
          <path d="M21.5 2.5 2 10.5l5 2 2 6 3-4 5 4 4.5-16z"/>
        </svg>
        Telegram
      </h2>
      <n-tag size="small" :type="loginState === 'logged_in' ? 'success' : loginState === 'busy' ? 'warning' : 'default'">
        {{ loginLabel }}
      </n-tag>
      <n-button size="small" quaternary @click="showSettings = true">设置</n-button>
    </div>

    <n-alert v-if="!tdlReady" type="warning" class="tdl-warn">
      <div class="warn-row">
        <span>未检测到 tdl 可执行文件，TG 功能不可用。</span>
        <n-button size="tiny" type="primary" :loading="downloading" @click="downloadTdl">自动下载 tdl</n-button>
      </div>
    </n-alert>

    <!-- 未登录 -->
    <div v-if="loginState !== 'logged_in'" class="login-card">
      <div class="login-title">登录 Telegram</div>
      <p class="login-desc">登录后即可解析 t.me 链接、在线播放与下载频道文件。登录状态跨重启有效。</p>
      <div class="login-actions">
        <n-button type="primary" :loading="loginStarting" @click="startLogin('qr')">扫码登录</n-button>
        <n-button :loading="loginStarting" @click="showPhone = true">手机号登录</n-button>
        <n-button quaternary @click="detectLogin">重新检测</n-button>
      </div>

      <div v-if="loginSession.state === 'qr' && qrText" class="qr-box">
        <pre class="qr-text">{{ qrText }}</pre>
        <p class="qr-hint">用 Telegram 手机端扫描上方二维码（在终端字体下显示）</p>
      </div>
      <div v-else-if="['code','password','select'].includes(loginSession.state)" class="code-box">
        <p class="code-hint">{{ inputHint }}</p>
        <div class="code-row">
          <n-input v-model:value="inputValue" :placeholder="inputPlaceholder" @keyup.enter="submitInput" />
          <n-button type="primary" @click="submitInput">提交</n-button>
        </div>
      </div>
      <div v-else-if="loginSession.state === 'starting'" class="code-box">
        <n-spin size="small" /> <span class="code-hint">正在启动登录…</span>
      </div>
      <div v-else-if="loginSession.state === 'failed'" class="code-box">
        <p class="code-hint err">{{ loginSession.error || '登录失败' }}</p>
      </div>
    </div>

    <!-- 已登录：解析 -->
    <template v-else>
      <div v-if="!session" class="input-state">
        <n-input
          v-model:value="inputText"
          type="textarea"
          placeholder="粘贴 Telegram 链接（每行一个），例如：https://t.me/channel/123"
          :autosize="{ minRows: 3, maxRows: 6 }"
        />
        <div class="input-row">
          <n-button type="primary" :loading="previewing" :disabled="!inputText.trim()" @click="doPreview">解析</n-button>
        </div>
      </div>

      <template v-else>
        <div class="result-head">
          <n-button size="small" quaternary @click="backToInput">重新解析</n-button>
          <div class="result-title">共 {{ session.files.length }} 个文件</div>
          <n-button size="small" quaternary @click="stopSession">关闭会话</n-button>
        </div>
        <div v-if="session.files.length === 0" class="empty"><n-empty description="未找到文件" /></div>
        <div v-else class="file-list">
          <div v-for="f in session.files" :key="f.href" class="file-row">
            <div class="file-icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg>
            </div>
            <div class="file-main">
              <div class="file-name" :title="f.name">{{ f.name }}</div>
              <div class="file-meta">
                <span>{{ formatSize(f.size) }}</span>
                <span v-if="!f.playable" class="noplay">需下载后播放</span>
              </div>
            </div>
            <div class="file-actions">
              <n-button size="tiny" type="primary" ghost :disabled="!f.playable" @click="playFile(f)">播放</n-button>
              <n-button size="tiny" ghost :loading="busyHref === f.href" @click="downloadFile(f)">下载</n-button>
            </div>
          </div>
        </div>
      </template>
    </template>

    <!-- 手机号登录弹窗 -->
    <n-modal v-model:show="showPhone" preset="card" title="手机号登录" style="max-width: 440px">
      <n-input v-model:value="phone" placeholder="手机号（含国家码，如 +8613800138000）" />
      <template #footer>
        <div style="display:flex;justify-content:flex-end;gap:8px">
          <n-button @click="showPhone = false">取消</n-button>
          <n-button type="primary" @click="startLogin('code')">开始</n-button>
        </div>
      </template>
    </n-modal>

    <!-- 设置弹窗 -->
    <n-modal v-model:show="showSettings" preset="card" title="Telegram 设置" style="max-width: 560px">
      <n-space vertical :size="14">
        <div>
          <div class="set-label">tdl 可执行文件路径</div>
          <n-input v-model:value="cfg.tdl_path" placeholder="留空则自动发现（PATH 或项目 tdl/ 目录）" />
        </div>
        <div>
          <div class="set-label">命名空间（ns）</div>
          <n-input v-model:value="cfg.ns" placeholder="default" />
        </div>
        <div>
          <div class="set-label">代理（留空用全局代理）</div>
          <n-input v-model:value="cfg.proxy" placeholder="socks5://127.0.0.1:7890" />
        </div>
        <div>
          <div class="set-label">下载目录（留空用全局下载目录）</div>
          <n-input v-model:value="cfg.download_dir" placeholder="/path/to/downloads" />
        </div>
        <div class="set-grid">
          <div><div class="set-label">每文件并发</div><n-input-number v-model:value="cfg.connections" :min="1" :max="64" /></div>
          <div><div class="set-label">同时文件数</div><n-input-number v-model:value="cfg.file_concurrency" :min="1" :max="8" /></div>
        </div>
        <div class="set-grid">
          <div><div class="set-label">播放预取连接</div><n-input-number v-model:value="cfg.stream_connections" :min="1" :max="128" /></div>
          <div><div class="set-label">预取窗口 (MB)</div><n-input-number v-model:value="cfg.stream_window_mb" :min="8" :max="4096" /></div>
        </div>
        <div>
          <div class="set-label">仅下载扩展名（逗号分隔，留空=全部）</div>
          <n-input v-model:value="cfg.include" placeholder="mp4,mkv" />
        </div>
        <div class="tdl-line">
          tdl 状态：{{ tdl.hasTdl ? '已就绪' : '未找到' }}
          <n-button size="tiny" :loading="downloading" @click="downloadTdl">自动下载</n-button>
        </div>
      </n-space>
      <template #footer>
        <div style="display:flex;justify-content:flex-end;gap:8px">
          <n-button @click="showSettings = false">取消</n-button>
          <n-button type="primary" :loading="savingCfg" @click="saveCfg">保存</n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useMessage, NButton, NInput, NInputNumber, NTag, NAlert, NModal, NSpace, NEmpty, NSpin } from 'naive-ui'
import { tgAPI, type TgFile } from '@/api/tg'
import { formatSize } from '@/utils/format'
import BackTop from '@/components/BackTop.vue'

const message = useMessage()

const tdlReady = ref(true)
const tdl = ref<any>({ hasTdl: true })
const downloading = ref(false)
const loginState = ref('unknown')
const loginSession = ref<any>({ state: 'idle' })
const loginStarting = ref(false)
const qrText = ref('')
const inputValue = ref('')
const phone = ref('')
const showPhone = ref(false)
const showSettings = ref(false)
const savingCfg = ref(false)
const cfg = ref<any>({})

const inputText = ref('')
const previewing = ref(false)
const session = ref<{ sid: string; dir: string; files: TgFile[] } | null>(null)
const busyHref = ref('')
let pollTimer: number | undefined

const loginLabel = computed(() => ({
  logged_in: '已登录', logged_out: '未登录', busy: '会话被占用', unknown: '检测中…',
}[loginState.value] || '未知'))

const inputHint = computed(() => ({
  code: '请输入 Telegram 发送的验证码',
  password: '请输入两步验证密码',
  select: '请选择要登录的账号',
}[loginSession.value.state] || '请按提示输入'))
const inputPlaceholder = computed(() => loginSession.value.state === 'password' ? '两步验证密码' : '验证码')

async function loadConfig() {
  try {
    const res: any = await tgAPI.config()
    cfg.value = res.data || {}
    tdl.value = res.tdl || {}
    tdlReady.value = !!res.tdl?.hasTdl
    loginState.value = res.login?.loginState || 'unknown'
    loginSession.value = res.login?.session || { state: 'idle' }
    if (loginSession.value.qr) qrText.value = loginSession.value.qr
  } catch { /* ignore */ }
}

async function downloadTdl() {
  downloading.value = true
  try {
    await tgAPI.tdlDownload()
    message.success('tdl 已下载')
    await loadConfig()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '下载失败')
  } finally {
    downloading.value = false
  }
}

async function detectLogin() {
  const res: any = await tgAPI.detect()
  loginState.value = res.state
}

async function startLogin(kind: string) {
  if (kind === 'code' && !phone.value.trim()) { message.warning('请填写手机号'); return }
  showPhone.value = false
  loginStarting.value = true
  try {
    const res: any = await tgAPI.loginStart(kind, phone.value.trim())
    loginSession.value = res.data
    pollLogin()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '启动登录失败')
  } finally {
    loginStarting.value = false
  }
}

async function submitInput() {
  if (!inputValue.value.trim()) return
  try {
    await tgAPI.loginInput(inputValue.value.trim())
    inputValue.value = ''
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '提交失败')
  }
}

function pollLogin() {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = window.setInterval(async () => {
    try {
      const res: any = await tgAPI.login()
      loginSession.value = res.data?.session || {}
      loginState.value = res.data?.loginState || loginState.value
      if (loginSession.value.qr) qrText.value = loginSession.value.qr
      if (loginState.value === 'logged_in') {
        clearInterval(pollTimer)
        pollTimer = undefined
        message.success('登录成功')
      }
    } catch { /* ignore */ }
  }, 2000)
}

async function doPreview() {
  const text = inputText.value.trim()
  if (!text) return
  previewing.value = true
  try {
    const res: any = await tgAPI.preview(text)
    session.value = res.data
    if (!res.data.files.length) message.warning('未解析到文件')
    else message.success(`解析到 ${res.data.files.length} 个文件`)
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '解析失败')
  } finally {
    previewing.value = false
  }
}

async function stopSession() {
  if (!session.value) return
  try {
    await tgAPI.stop(session.value.sid)
    session.value = null
  } catch (e: any) {
    // 会话仍在播放中（后端 409 保护）：保留会话，提示用户先关播放页
    const detail = e?.response?.data?.detail || ''
    if (detail.includes('播放')) {
      message.warning('该会话正在播放中，请先关闭播放页')
    } else {
      session.value = null
    }
  }
}

function backToInput() {
  stopSession()
}

function playFile(f: TgFile) {
  if (!session.value) return
  const url = tgAPI.streamUrl(session.value.sid, f.href)
  window.open(`/play?url=${encodeURIComponent(url)}&title=${encodeURIComponent(f.name)}`, '_blank')
}

async function downloadFile(f: TgFile) {
  if (!session.value) return
  busyHref.value = f.href
  try {
    await tgAPI.download(session.value.sid, f.href, f.name)
    message.success(`已加入下载队列：${f.name}`)
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '下载失败')
  } finally {
    busyHref.value = ''
  }
}

async function saveCfg() {
  savingCfg.value = true
  try {
    await tgAPI.saveConfig(cfg.value)
    message.success('已保存')
    showSettings.value = false
    await loadConfig()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '保存失败')
  } finally {
    savingCfg.value = false
  }
}

onMounted(async () => {
  await loadConfig()
  if (loginState.value !== 'logged_in') detectLogin()
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.tg-page { padding: 20px; max-width: 1100px; margin: 0 auto; min-height: 100vh; }
.page-header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.page-header h2 { margin: 0; font-size: 20px; flex: 1; }
.tdl-warn { margin-bottom: 16px; }
.warn-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }

.login-card { border: 1px solid rgba(128,128,128,0.15); border-radius: 12px; padding: 24px; background: var(--n-card-color); }
.login-title { font-size: 16px; font-weight: 600; margin-bottom: 6px; }
.login-desc { font-size: 13px; color: #888; margin-bottom: 16px; line-height: 1.6; }
.login-actions { display: flex; gap: 10px; flex-wrap: wrap; }
.qr-box { margin-top: 20px; text-align: center; }
.qr-text { font-family: monospace; font-size: 6px; line-height: 6px; white-space: pre; background: #000; color: #fff; padding: 12px; border-radius: 8px; display: inline-block; }
.qr-hint { font-size: 12px; color: #888; margin-top: 8px; }
.code-box { margin-top: 20px; }
.code-hint { font-size: 13px; color: #aaa; margin-bottom: 8px; }
.code-hint.err { color: #e88080; }
.code-row { display: flex; gap: 10px; }

.input-state { display: flex; flex-direction: column; gap: 12px; }
.input-row { display: flex; gap: 10px; }
.result-head { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.result-title { flex: 1; font-size: 14px; color: #aaa; }
.empty { padding: 40px 0; }

.file-list { display: flex; flex-direction: column; gap: 2px; }
.file-row { display: flex; align-items: center; gap: 12px; padding: 10px 12px; border-radius: 8px; transition: background 0.15s; }
.file-row:hover { background: rgba(128,128,128,0.08); }
.file-icon { color: #888; display: flex; flex-shrink: 0; }
.file-main { flex: 1; min-width: 0; }
.file-name { font-size: 14px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-meta { font-size: 12px; color: #888; display: flex; gap: 12px; margin-top: 2px; }
.noplay { color: #e0a030; }
.file-actions { display: flex; gap: 6px; flex-shrink: 0; }

.set-label { font-size: 13px; color: #999; margin-bottom: 6px; }
.set-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.tdl-line { font-size: 13px; color: #aaa; display: flex; align-items: center; gap: 10px; }
</style>
