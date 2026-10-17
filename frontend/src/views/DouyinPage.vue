<template>
  <div class="dy-page">
    <BackTop />
    <div class="page-header">
      <h2>
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:-4px;margin-right:6px">
          <path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>
        </svg>
        抖音解析
      </h2>
      <n-button size="small" quaternary @click="showCookie = true">
        <template #icon><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg></template>
        风控 Cookie
      </n-button>
    </div>

    <!-- 输入态 -->
    <div v-if="!result" class="input-state">
      <n-input
        v-model:value="inputText"
        type="textarea"
        placeholder="粘贴抖音分享链接或整段分享文案，例如：7.43 复制打开抖音，看看【某某】的作品 https://v.douyin.com/xxxx/"
        :autosize="{ minRows: 3, maxRows: 6 }"
        @keydown.ctrl.enter="doResolve"
      />
      <div class="input-row">
        <n-button type="primary" :loading="resolving" :disabled="!inputText.trim()" @click="doResolve">
          解析
        </n-button>
        <span class="hint">支持视频、图集；解析后可直接播放或下载</span>
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
          <span class="dy-badge">{{ result.type === 'images' ? '图集' : '视频' }}</span>
          <span class="dy-title" :title="result.title">{{ result.title || '无标题' }}</span>
          <span v-if="result.author" class="dy-author">@{{ result.author }}</span>
        </div>
      </div>

      <!-- 视频 -->
      <div v-if="result.type === 'video' && result.video" class="media-card">
        <div class="video-wrap">
          <video :src="douyinAPI.streamUrl(result.video.token)" controls preload="metadata"></video>
        </div>
        <div class="media-actions">
          <n-button type="primary" :loading="busy" @click="downloadOne(result.video)">下载视频</n-button>
          <n-button v-if="result.cover" ghost :loading="busy" @click="downloadOne(result.cover!)">下载封面</n-button>
          <n-button v-if="result.music" ghost :loading="busy" @click="downloadOne(result.music!)">下载音乐</n-button>
        </div>
      </div>

      <!-- 图集 -->
      <template v-else-if="result.type === 'images' && result.images.length">
        <div class="media-actions" style="margin-bottom:14px">
          <n-button type="primary" :loading="busy" @click="downloadAll">下载全部（{{ result.images.length }} 张）</n-button>
        </div>
        <div class="img-grid">
          <div v-for="img in result.images" :key="img.token" class="img-cell">
            <img :src="douyinAPI.streamUrl(img.token)" loading="lazy" :alt="`图 ${img.index}`" />
            <button class="img-dl" :title="`下载第 ${img.index} 张`" @click="downloadOne(img)">↓</button>
          </div>
        </div>
      </template>

      <n-alert v-else type="warning">未获取到可播放/下载的媒体</n-alert>
    </template>

    <!-- Cookie 弹窗 -->
    <n-modal v-model:show="showCookie" preset="card" title="抖音 Cookie（推荐配置）" style="max-width: 620px">
      <div class="cookie-hint">
        <b>抖音已开启 uifid 风控</b>，纯匿名解析会被拦截。粘贴一次浏览器 Cookie 即可长期使用：
        <ol class="cookie-steps">
          <li>电脑浏览器打开 <code>https://www.douyin.com</code> 并随便刷一下（确保已加载视频）</li>
          <li>按 <code>F12</code> → <b>Network</b> → 点任意一条请求 → <b>Headers</b> → 复制 <b>Cookie</b> 整行</li>
          <li>粘到下面；UA 也请一并复制（同一浏览器，否则签名不匹配）</li>
        </ol>
        <div class="cookie-keys">必须包含 <code>ttwid</code>；强烈建议含 <code>uifid</code>、<code>msToken</code></div>
      </div>
      <div class="field-label">Cookie</div>
      <n-input v-model:value="cookieInput" type="textarea" placeholder="ttwid=1%7C...; uifid=...; msToken=..." :autosize="{ minRows: 4, maxRows: 10 }" />
      <div class="field-label" style="margin-top:12px">User-Agent（可选，建议填写）</div>
      <n-input v-model:value="uaInput" placeholder="Mozilla/5.0 (Windows NT 10.0; Win64; x64) ... Chrome/131.0.0.0 Safari/537.36" />
      <div v-if="verifyMsg" class="verify-msg" :class="{ ok: verifyOk }">{{ verifyMsg }}</div>
      <template #footer>
        <div style="display:flex;justify-content:space-between;gap:8px">
          <n-button :loading="verifying" :disabled="!cookieInput.trim()" @click="verifyCookie">验证 Cookie</n-button>
          <div style="display:flex;gap:8px">
            <n-button @click="showCookie = false">取消</n-button>
            <n-button type="primary" :loading="savingCookie" @click="saveCookie">保存</n-button>
          </div>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useMessage, NInput, NButton, NAlert, NModal } from 'naive-ui'
import { douyinAPI, type DouyinMedia, type DouyinResult } from '@/api/douyin'
import BackTop from '@/components/BackTop.vue'

const message = useMessage()

const inputText = ref('')
const resolving = ref(false)
const result = ref<DouyinResult | null>(null)
const busy = ref(false)
const showCookie = ref(false)
const cookieInput = ref('')
const uaInput = ref('')
const savingCookie = ref(false)
const verifying = ref(false)
const verifyMsg = ref('')
const verifyOk = ref(false)

async function doResolve() {
  const text = inputText.value.trim()
  if (!text) return
  resolving.value = true
  try {
    const res: any = await douyinAPI.resolve(text)
    result.value = res.data
    if (res.data.type === 'video') message.success('解析成功，可直接播放')
    else if (res.data.type === 'images') message.success(`解析成功，共 ${res.data.images.length} 张图`)
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '解析失败')
  } finally {
    resolving.value = false
  }
}

function backToInput() {
  result.value = null
}

async function downloadOne(media: DouyinMedia) {
  busy.value = true
  try {
    const res = await douyinAPI.download(media.token)
    message.success(`已加入下载队列：${res.name}`)
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '下载失败')
  } finally {
    busy.value = false
  }
}

async function downloadAll() {
  if (!result.value) return
  busy.value = true
  try {
    const tokens = result.value.images.map(i => i.token)
    const res = await douyinAPI.downloadAll(tokens)
    message.success(`已加入下载队列：${res.count} 个文件`)
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '下载失败')
  } finally {
    busy.value = false
  }
}

async function saveCookie() {
  savingCookie.value = true
  try {
    await douyinAPI.setConfig(cookieInput.value.trim(), uaInput.value.trim())
    message.success('已保存')
    showCookie.value = false
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '保存失败')
  } finally {
    savingCookie.value = false
  }
}

async function verifyCookie() {
  verifying.value = true
  verifyMsg.value = ''
  try {
    // 先保存再验证，保证服务端用的是当前输入
    await douyinAPI.setConfig(cookieInput.value.trim(), uaInput.value.trim())
    const res: any = await douyinAPI.verify()
    verifyOk.value = !!res.data?.ok
    verifyMsg.value = res.data?.detail || (verifyOk.value ? 'Cookie 有效' : 'Cookie 无效')
  } catch (e: any) {
    verifyOk.value = false
    verifyMsg.value = e?.response?.data?.detail || '验证失败'
  } finally {
    verifying.value = false
  }
}

onMounted(async () => {
  try {
    const res: any = await douyinAPI.config()
    uaInput.value = res.data?.user_agent || ''
  } catch { /* ignore */ }
})
</script>

<style scoped>
.dy-page { padding: 20px; max-width: 1100px; margin: 0 auto; min-height: 100vh; }
.page-header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.page-header h2 { margin: 0; font-size: 20px; flex: 1; }
.input-state { display: flex; flex-direction: column; gap: 12px; }
.input-row { display: flex; align-items: center; gap: 12px; }
.hint { font-size: 12px; color: #888; }

.result-head { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }
.result-title { flex: 1; display: flex; align-items: center; gap: 8px; min-width: 0; }
.dy-badge { font-size: 12px; padding: 2px 8px; border-radius: 6px; background: rgba(0,170,238,0.15); color: var(--n-primary-color); flex-shrink: 0; }
.dy-title { font-size: 15px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dy-author { font-size: 13px; color: #888; flex-shrink: 0; }

.media-card { border: 1px solid rgba(128,128,128,0.15); border-radius: 12px; padding: 14px; background: var(--n-card-color); }
.video-wrap { border-radius: 10px; overflow: hidden; background: #000; display: flex; justify-content: center; }
.video-wrap video { width: 100%; max-width: 420px; max-height: 70vh; display: block; }
.media-actions { display: flex; gap: 10px; margin-top: 14px; flex-wrap: wrap; }

.img-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 12px; }
.img-cell { position: relative; border-radius: 10px; overflow: hidden; background: var(--n-card-color); aspect-ratio: 3/4; }
.img-cell img { width: 100%; height: 100%; object-fit: cover; display: block; }
.img-dl { position: absolute; right: 8px; bottom: 8px; width: 30px; height: 30px; border-radius: 50%; border: none; background: rgba(0,0,0,0.55); color: #fff; cursor: pointer; font-size: 15px; line-height: 1; }
.img-dl:hover { background: var(--n-primary-color); }

.cookie-hint { font-size: 13px; color: #999; margin-bottom: 12px; line-height: 1.7; }
.cookie-steps { margin: 8px 0 8px 18px; padding: 0; }
.cookie-steps li { margin-bottom: 4px; }
.cookie-hint code { background: rgba(128,128,128,0.18); padding: 1px 5px; border-radius: 3px; font-size: 12px; }
.cookie-keys { font-size: 12px; color: #7a7a7a; }
.field-label { font-size: 13px; color: #999; margin-bottom: 6px; }
.verify-msg { margin-top: 12px; font-size: 13px; color: #e88080; line-height: 1.6; }
.verify-msg.ok { color: #5fbf7f; }
</style>
