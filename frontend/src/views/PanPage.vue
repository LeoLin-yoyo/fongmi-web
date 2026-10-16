<template>
  <div class="pan-page">
    <BackTop />
    <div class="page-header">
      <h2>
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:-4px;margin-right:6px">
          <path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z"/>
        </svg>
        网盘解析
      </h2>
      <n-button size="small" quaternary @click="showAccounts = true">
        <template #icon><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="8" r="4"/><path d="M4 21v-1a6 6 0 0 1 12 0v1"/></svg></template>
        网盘账号
      </n-button>
    </div>

    <!-- 输入态 -->
    <div v-if="!session" class="input-state">
      <n-input
        v-model:value="inputText"
        type="textarea"
        placeholder="粘贴网盘分享链接（可带提取码），例如：https://pan.quark.cn/s/xxxx 提取码：abcd"
        :autosize="{ minRows: 3, maxRows: 6 }"
        @keydown.ctrl.enter="doResolve"
      />
      <div class="input-row">
        <n-input v-model:value="manualPwd" placeholder="提取码（可选）" class="pwd-input" clearable />
        <n-button type="primary" :loading="resolving" :disabled="!inputText.trim()" @click="doResolve">
          解析
        </n-button>
      </div>
      <div class="platform-hint">
        <span class="hint-label">支持：</span>
        <span v-for="p in platforms" :key="p.key" class="plat-chip" :class="{ active: hasAccount(p.key) }" :title="p.label">
          {{ p.label }}
        </span>
      </div>
    </div>

    <!-- 结果态 -->
    <template v-else>
      <div class="result-head">
        <n-button size="small" quaternary @click="backToInput">
          <template #icon><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg></template>
          重新解析
        </n-button>
        <div class="result-title">
          <span class="plat-badge">{{ session.label }}</span>
          <span class="share-title" :title="session.title">{{ session.title || '分享文件' }}</span>
        </div>
        <n-button size="small" :loading="refreshing" @click="refreshRoot">刷新</n-button>
      </div>

      <n-alert v-if="session.notice" type="warning" :show-icon="true" class="guest-notice">
        {{ session.notice }}
      </n-alert>

      <div class="breadcrumb">
        <button class="crumb" @click="goCrumb(-1)">根目录</button>
        <template v-for="(c, i) in crumbs" :key="c.fid">
          <span class="crumb-sep">/</span>
          <button class="crumb" @click="goCrumb(i)">{{ c.name }}</button>
        </template>
      </div>

      <div v-if="loading" class="loading-area"><n-spin size="large" /></div>

      <template v-else-if="files.length === 0">
        <n-empty description="该目录为空" />
      </template>

      <div v-else class="file-list">
        <div
          v-for="f in sortedFiles"
          :key="f.fid"
          class="file-row"
          :class="{ 'is-dir': f.isdir }"
          @click="onFileClick(f)"
        >
          <div class="file-icon">
            <svg v-if="f.isdir" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
            <svg v-else width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg>
          </div>
          <div class="file-main">
            <div class="file-name" :title="f.fname">{{ f.fname }}</div>
            <div class="file-meta">
              <span v-if="!f.isdir">{{ formatSize(f.fsize) }}</span>
              <span v-else>文件夹</span>
              <span v-if="f.updated_at" class="file-time">{{ f.updated_at }}</span>
            </div>
          </div>
          <div class="file-actions" @click.stop>
            <template v-if="!f.isdir">
              <n-button size="tiny" type="primary" ghost :loading="busyFid === f.fid" @click="playFile(f)">播放</n-button>
              <n-button size="tiny" ghost :loading="busyFid === f.fid" @click="downloadFile(f)">下载</n-button>
            </template>
            <n-button v-else size="tiny" quaternary @click="openDir(f)">打开</n-button>
          </div>
        </div>
      </div>
    </template>

    <!-- 账号管理弹窗 -->
    <n-modal v-model:show="showAccounts" preset="card" title="网盘账号" style="max-width: 640px">
      <div class="acct-hint">粘贴浏览器 Cookie 即可登录（F12 → 网络 → 任意请求 → 复制 Cookie 请求头）。Cookie 加密保存在本机。</div>
      <div v-for="a in accounts" :key="a.platform" class="acct-row">
        <div class="acct-info">
          <div class="acct-name">
            {{ a.label }}
            <n-tag v-if="a.has_cookie && a.valid" size="tiny" type="success">已登录{{ a.nickname ? '：' + a.nickname : '' }}</n-tag>
            <n-tag v-else-if="a.has_cookie" size="tiny" type="warning">登录态失效</n-tag>
            <n-tag v-else size="tiny">未登录</n-tag>
          </div>
          <div class="acct-note">{{ a.guest_note }}</div>
        </div>
        <div class="acct-actions">
          <n-button size="tiny" @click="openCookieEditor(a)">{{ a.has_cookie ? '更新' : '登录' }}</n-button>
          <n-button v-if="a.has_cookie" size="tiny" :loading="checking === a.platform" @click="checkAccount(a)">检测</n-button>
          <n-button v-if="a.has_cookie" size="tiny" type="error" ghost @click="removeAccount(a)">退出</n-button>
        </div>
      </div>
    </n-modal>

    <n-modal v-model:show="showCookieEditor" preset="card" :title="`登录 ${editingAccount?.label || ''}`" style="max-width: 560px">
      <n-input v-model:value="cookieInput" type="textarea" placeholder="粘贴 Cookie 字符串，例如 __pus=xxx; __puus=yyy" :autosize="{ minRows: 4, maxRows: 10 }" />
      <template #footer>
        <div style="display:flex;justify-content:flex-end;gap:8px">
          <n-button @click="showCookieEditor = false">取消</n-button>
          <n-button type="primary" :loading="savingCookie" @click="saveCookie">保存并校验</n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useMessage, NInput, NButton, NAlert, NSpin, NEmpty, NModal, NTag } from 'naive-ui'
import { panAPI, type PanFile, type PanSession } from '@/api/pan'
import { formatSize } from '@/utils/format'
import BackTop from '@/components/BackTop.vue'

const message = useMessage()

const inputText = ref('')
const manualPwd = ref('')
const resolving = ref(false)
const refreshing = ref(false)
const loading = ref(false)
const busyFid = ref('')

const platforms = ref<{ key: string; label: string }[]>([])
const session = ref<PanSession | null>(null)
const files = ref<PanFile[]>([])
const crumbs = ref<{ fid: string; name: string }[]>([])

const showAccounts = ref(false)
const accounts = ref<any[]>([])
const checking = ref('')
const showCookieEditor = ref(false)
const editingAccount = ref<any>(null)
const cookieInput = ref('')
const savingCookie = ref(false)

const sortedFiles = computed(() =>
  [...files.value].sort((a, b) => (a.isdir === b.isdir ? a.fname.localeCompare(b.fname, 'zh') : a.isdir ? -1 : 1)),
)
const currentFid = computed(() => crumbs.value.length ? crumbs.value[crumbs.value.length - 1].fid : '0')
const currentPath = computed(() => crumbs.value.map(c => c.name).join('/'))

function hasAccount(key: string) {
  return accounts.value.some(a => a.platform === key && a.has_cookie && a.valid)
}

async function loadPlatforms() {
  try {
    const res: any = await panAPI.platforms()
    platforms.value = res.data || []
  } catch { /* ignore */ }
}

async function loadAccounts() {
  try {
    const res: any = await panAPI.accounts()
    accounts.value = res.data || []
  } catch { /* ignore */ }
}

async function doResolve() {
  const text = inputText.value.trim()
  if (!text) return
  resolving.value = true
  try {
    const res: any = await panAPI.resolve(text, manualPwd.value.trim())
    session.value = res.session
    files.value = res.files || []
    crumbs.value = []
    message.success(`已解析「${res.session.title || res.session.label}」，共 ${files.value.length} 项`)
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '解析失败')
  } finally {
    resolving.value = false
  }
}

function backToInput() {
  session.value = null
  files.value = []
  crumbs.value = []
}

async function refreshRoot() {
  if (!session.value) return
  refreshing.value = true
  crumbs.value = []
  await loadDir('0')
  refreshing.value = false
}

async function loadDir(fid: string) {
  if (!session.value) return
  loading.value = true
  try {
    const res: any = await panAPI.browse(
      session.value.platform, session.value.share_id, session.value.passcode, fid, currentPath.value,
    )
    files.value = res.files || []
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '列目录失败')
  } finally {
    loading.value = false
  }
}

function openDir(f: PanFile) {
  crumbs.value.push({ fid: f.fid, name: f.fname })
  loadDir(f.fid)
}

function goCrumb(idx: number) {
  crumbs.value = crumbs.value.slice(0, idx + 1)
  loadDir(idx < 0 ? '0' : crumbs.value[idx].fid)
}

function onFileClick(f: PanFile) {
  if (f.isdir) openDir(f)
}

async function playFile(f: PanFile) {
  if (!session.value) return
  busyFid.value = f.fid
  try {
    const res: any = await panAPI.link(
      session.value.platform, session.value.share_id, session.value.passcode, f.fid, currentFid.value,
    )
    if (!res.playable) {
      message.warning(`「${res.name}」浏览器无法直接播放，建议下载后用本地播放器`)
    }
    const url = res.stream_path
    window.open(`/play?url=${encodeURIComponent(url)}&title=${encodeURIComponent(res.name)}`, '_blank')
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '取直链失败')
  } finally {
    busyFid.value = ''
  }
}

async function downloadFile(f: PanFile) {
  if (!session.value) return
  busyFid.value = f.fid
  try {
    const res: any = await panAPI.link(
      session.value.platform, session.value.share_id, session.value.passcode, f.fid, currentFid.value,
    )
    await panAPI.download(res.token)
    message.success(`已加入下载队列：${res.name}`)
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '下载失败')
  } finally {
    busyFid.value = ''
  }
}

// ---- 账号 ----
function openCookieEditor(a: any) {
  editingAccount.value = a
  cookieInput.value = ''
  showCookieEditor.value = true
}

async function saveCookie() {
  if (!editingAccount.value) return
  savingCookie.value = true
  try {
    const res: any = await panAPI.saveAccount(editingAccount.value.platform, cookieInput.value.trim())
    if (res.code === 0) {
      message.success('登录成功')
      showCookieEditor.value = false
    } else {
      message.warning(res.detail || '已保存，但登录态校验未通过')
      showCookieEditor.value = false
    }
    await loadAccounts()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '保存失败')
  } finally {
    savingCookie.value = false
  }
}

async function checkAccount(a: any) {
  checking.value = a.platform
  try {
    const res: any = await panAPI.checkAccount(a.platform)
    if (res.data?.valid) message.success(`登录态有效${res.data.nickname ? '：' + res.data.nickname : ''}`)
    else message.error(res.data?.detail || '登录态无效')
    await loadAccounts()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '检测失败')
  } finally {
    checking.value = ''
  }
}

async function removeAccount(a: any) {
  try {
    await panAPI.deleteAccount(a.platform)
    message.success('已退出')
    await loadAccounts()
  } catch {
    message.error('操作失败')
  }
}

onMounted(() => {
  loadPlatforms()
  loadAccounts()
})
</script>

<style scoped>
.pan-page { padding: 20px; max-width: 1200px; margin: 0 auto; min-height: 100vh; }
.page-header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.page-header h2 { margin: 0; font-size: 20px; flex: 1; }
.input-state { display: flex; flex-direction: column; gap: 12px; }
.input-row { display: flex; gap: 10px; }
.pwd-input { max-width: 220px; }
.platform-hint { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-top: 4px; }
.hint-label { font-size: 13px; color: #888; }
.plat-chip { font-size: 12px; padding: 3px 10px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.12); color: #999; }
.plat-chip.active { border-color: var(--n-primary-color); color: var(--n-primary-color); }

.result-head { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.result-title { flex: 1; display: flex; align-items: center; gap: 8px; min-width: 0; }
.plat-badge { font-size: 12px; padding: 2px 8px; border-radius: 6px; background: rgba(0,170,238,0.15); color: var(--n-primary-color); flex-shrink: 0; }
.share-title { font-size: 15px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.guest-notice { margin-bottom: 12px; }

.breadcrumb { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; margin-bottom: 12px; font-size: 13px; }
.crumb { background: none; border: none; color: #999; cursor: pointer; padding: 2px 6px; border-radius: 4px; font-size: 13px; }
.crumb:hover { color: var(--n-primary-color); background: rgba(128,128,128,0.1); }
.crumb-sep { color: #555; }
.loading-area { display: flex; justify-content: center; padding: 60px 0; }

.file-list { display: flex; flex-direction: column; gap: 2px; }
.file-row { display: flex; align-items: center; gap: 12px; padding: 10px 12px; border-radius: 8px; cursor: default; transition: background 0.15s; }
.file-row:hover { background: rgba(128,128,128,0.08); }
.file-row.is-dir { cursor: pointer; }
.file-icon { color: #888; display: flex; flex-shrink: 0; }
.file-row.is-dir .file-icon { color: var(--n-primary-color); }
.file-main { flex: 1; min-width: 0; }
.file-name { font-size: 14px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-meta { font-size: 12px; color: #888; display: flex; gap: 12px; margin-top: 2px; }
.file-actions { display: flex; gap: 6px; flex-shrink: 0; }

.acct-hint { font-size: 12px; color: #888; margin-bottom: 14px; line-height: 1.6; }
.acct-row { display: flex; align-items: center; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid rgba(128,128,128,0.12); }
.acct-row:last-child { border-bottom: none; }
.acct-name { font-size: 14px; display: flex; align-items: center; gap: 8px; }
.acct-note { font-size: 12px; color: #888; margin-top: 4px; }
.acct-actions { display: flex; gap: 6px; flex-shrink: 0; }
</style>
