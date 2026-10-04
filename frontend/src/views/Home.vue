<template>
  <div class="home-page">
    <BackTop />
    <div v-if="initLoading" class="init-loading">
      <n-spin size="large" />
      <p style="margin-top:12px;color:#888">加载中...</p>
    </div>

    <div v-else-if="!hasSite" class="empty-state">
      <div class="empty-icon">
        <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="color:#555">
          <rect x="2" y="7" width="20" height="15" rx="2" ry="2"/>
          <polygon points="10 11 16 14.5 10 18 10 11"/>
        </svg>
      </div>
      <h2>欢迎来到 FongMi TV</h2>
      <p>请先导入您的订阅配置即可开始观看</p>
      <n-button type="primary" size="large" round @click="showGuide = true">
        快速开始（三步导入）
      </n-button>
      <n-button quaternary style="margin-top:12px" @click="$router.push('/setting')">
        前往设置手动导入
      </n-button>

      <n-modal v-model:show="showGuide" title="快速开始" preset="card" style="max-width:480px">
        <div class="guide-steps">
          <div class="guide-step">
            <div class="step-num">1</div>
            <div class="step-content">
              <div class="step-title">一键导入示例源</div>
              <div class="step-desc">点击下方按钮，自动加载公开测试订阅源</div>
            </div>
          </div>
          <div class="guide-step">
            <div class="step-num">2</div>
            <div class="step-content">
              <div class="step-title">浏览首页</div>
              <div class="step-desc">选择站点后即可浏览热播内容</div>
            </div>
          </div>
          <div class="guide-step">
            <div class="step-num">3</div>
            <div class="step-content">
              <div class="step-title">开始观看</div>
              <div class="step-desc">点击任意视频即可播放，享受聚合体验</div>
            </div>
          </div>
        </div>
        <n-button type="primary" block :loading="importingDemo" @click="importDemoSource" style="margin-top:16px">
          一键导入示例源
        </n-button>
      </n-modal>
    </div>

    <template v-else>
      <!-- Continue Watching -->
      <div v-if="continueList.length" class="home-section">
        <div class="section-header">
          <h3><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:-3px;margin-right:6px"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>继续观看</h3>
          <router-link to="/history" class="section-more">查看全部</router-link>
        </div>
        <div class="rail-wrap">
          <button class="rail-arrow left" aria-label="向左滚动" @click="scrollRail($event, -1)"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m15 18-6-6 6-6"/></svg></button>
          <div class="rail-scroll" @wheel="onRailWheel">
            <div class="rail-track">
              <div v-for="item in continueList" :key="item.id" class="rail-card continue-card" @click="goContinue(item)">
                <div class="rail-cover">
                  <img :src="imgUrl(item.pic, item.name) || defaultPic" :alt="item.name" loading="lazy" />
                  <div class="continue-progress" v-if="item.duration > 0">
                    <div class="progress-fill" :style="{ width: Math.min(100, (item.position / item.duration) * 100) + '%' }"></div>
                  </div>
                  <div class="cover-overlay"><span class="play-icon">▶</span></div>
                </div>
                <div class="rail-info">
                  <div class="rail-name">{{ item.name }}</div>
                  <div class="rail-meta">{{ episodeLabel(item.episode) }}</div>
                </div>
              </div>
            </div>
          </div>
          <button class="rail-arrow right" aria-label="向右滚动" @click="scrollRail($event, 1)"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m9 18 6-6-6-6"/></svg></button>
        </div>
      </div>

      <!-- Cold Start: interest selection -->
      <div v-if="showColdStart" class="home-section cold-start">
        <div class="section-header">
          <h3>🎯 选择你感兴趣的类型</h3>
          <span class="section-more" @click="showColdStart = false">跳过</span>
        </div>
        <div class="interest-grid">
          <button v-for="t in interestTypes" :key="t.key"
            :class="['interest-btn', { active: selectedInterests.includes(t.key) }]"
            @click="toggleInterest(t.key)">
            {{ t.name }}
          </button>
        </div>
        <n-button type="primary" size="small" :disabled="!selectedInterests.length" @click="applyInterests" style="margin-top:12px">
          开始浏览 ({{ selectedInterests.length }})
        </n-button>
      </div>

      <!-- Hot/Popular Rail -->
      <div class="home-section">
        <div class="section-header">
          <h3>🔥 热播推荐</h3>
          <div class="site-select-mini">
            <n-select
              v-model:value="selectedSite"
              :options="vodSiteOptions"
              size="small"
              style="width:160px"
              placeholder="选择站点"
              filterable
              @update:value="onSiteChange"
            />
          </div>
        </div>
        <div class="rail-wrap">
          <button class="rail-arrow left" aria-label="向左滚动" @click="scrollRail($event, -1)"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m15 18-6-6 6-6"/></svg></button>
          <div class="rail-scroll" @wheel="onRailWheel">
            <div class="rail-track">
              <div v-for="(video, idx) in hotVideos" :key="video.vod_id + idx" class="rail-card" @click="goDetail(video.vod_id)">
                <div class="rail-cover">
                  <img :src="imgUrl(video.vod_pic, video.vod_name) || defaultPic" :alt="video.vod_name" loading="lazy" />
                  <div v-if="video.vod_remarks" class="cover-badge">{{ video.vod_remarks }}</div>
                  <div class="cover-overlay"><span class="play-icon">▶</span></div>
                </div>
                <div class="rail-info">
                  <div class="rail-name">{{ video.vod_name }}</div>
                  <div class="rail-meta">
                    <span v-if="video.vod_year">{{ video.vod_year }}</span>
                    <span v-if="video.vod_area" style="margin-left:4px">{{ video.vod_area }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <button class="rail-arrow right" aria-label="向右滚动" @click="scrollRail($event, 1)"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m9 18 6-6-6-6"/></svg></button>
        </div>
      </div>

      <!-- My Common Sources -->
      <div v-if="commonSites.length" class="home-section">
        <div class="section-header">
          <h3>📡 我的常用源</h3>
        </div>
        <div class="source-chips">
          <button v-for="s in commonSites" :key="s.key" class="source-chip" @click="switchSite(s.key)">
            {{ s.name }}
          </button>
        </div>
      </div>

      <!-- Recommended for you -->
      <div v-if="recommendedVideos.length" class="home-section">
        <div class="section-header">
          <h3>💡 猜你喜欢</h3>
        </div>
        <div class="rail-wrap">
          <button class="rail-arrow left" aria-label="向左滚动" @click="scrollRail($event, -1)"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m15 18-6-6 6-6"/></svg></button>
          <div class="rail-scroll" @wheel="onRailWheel">
            <div class="rail-track">
              <div v-for="video in recommendedVideos" :key="video.vod_id + video._site_key" class="rail-card" @click="goDetail(video.vod_id, video._site_key)">
                <div class="rail-cover">
                  <img :src="imgUrl(video.vod_pic, video.vod_name) || defaultPic" :alt="video.vod_name" loading="lazy" />
                  <div v-if="video.vod_remarks" class="cover-badge">{{ video.vod_remarks }}</div>
                  <div class="cover-overlay"><span class="play-icon">▶</span></div>
                </div>
                <div class="rail-info">
                  <div class="rail-name">{{ video.vod_name }}</div>
                  <div class="rail-meta">{{ video._site_name || video._site_key }}</div>
                </div>
              </div>
            </div>
          </div>
          <button class="rail-arrow right" aria-label="向右滚动" @click="scrollRail($event, 1)"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m9 18 6-6-6-6"/></svg></button>
        </div>
      </div>

      <!-- Site categories + video grid -->
      <div class="home-section">
        <div class="section-header">
          <h3>{{ currentCategoryName || '全部' }}{{ mergedCategory ? ' · 含子分类' : '' }}</h3>
          <div v-if="classes.length" class="class-tabs-mini" @wheel="onRailWheel">
            <button
              v-for="cls in classes" :key="cls.type_id"
              :class="['class-tab', { active: currentTid === cls.type_id }]"
              @click="onCategoryClick(cls.type_id, cls.type_name)"
            >{{ cls.type_name }}</button>
          </div>
        </div>

        <div v-if="loading" class="skeleton-grid">
          <div v-for="i in 12" :key="i" class="skeleton-card">
            <n-skeleton width="100%" :height="200" bordered />
          </div>
        </div>
        <template v-else>
          <div v-if="!videos.length" class="no-data"><p>暂无数据</p></div>
          <div class="video-grid">
            <div v-for="video in videos" :key="video.vod_id" class="video-card" @click="goDetail(video.vod_id)">
              <div class="card-cover">
                <img :src="imgUrl(video.vod_pic, video.vod_name) || defaultPic" :alt="video.vod_name" loading="lazy" />
                <div v-if="video.vod_remarks" class="cover-badge">{{ video.vod_remarks }}</div>
                <div class="cover-overlay"><span class="play-icon">▶</span></div>
              </div>
              <div class="card-info">
                <div class="video-name">{{ video.vod_name }}</div>
                <div class="video-meta">
                  <span v-if="video.vod_year" class="meta-tag">{{ video.vod_year }}</span>
                  <span v-if="video.vod_area" class="meta-tag">{{ video.vod_area }}</span>
                </div>
              </div>
            </div>
          </div>
        </template>
        <div v-if="videos.length && hasMore" ref="gridSentinel" class="load-more-sentinel">
          <n-spin v-if="loadingMore" size="small" />
        </div>
        <div v-if="videos.length && !hasMore && pagecount > 1" class="no-more-tip">已加载全部</div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { NButton, NSelect, NSpin, NSkeleton, NModal } from 'naive-ui'
import { imgUrl } from '@/api/img'
import { openPlayPage } from '@/utils/navigation'
import BackTop from '@/components/BackTop.vue'

const initLoading = ref(true)
const loading = ref(false)
const selectedSite = ref('')
const classes = ref<any[]>([])
const videos = ref<any[]>([])
const hotVideos = ref<any[]>([])
const recommendedVideos = ref<any[]>([])
const currentTid = ref('')
const currentCategoryName = ref('')
const currentPage = ref(1)
const pagecount = ref(1)
const gridSentinel = ref<HTMLElement | null>(null)
const loadingMore = ref(false)
const mergedCategory = ref(false)
const allSites = ref<any[]>([])
const continueList = ref<any[]>([])
const showColdStart = ref(false)
const showGuide = ref(false)
const importingDemo = ref(false)
const selectedInterests = ref<string[]>([])
const defaultPic = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 140"><rect fill="%23333" width="100" height="140"/></svg>'

const LIVE_KEYWORDS = ['直播', '体育', '赛事', '球']
const vodSites = computed(() => allSites.value.filter(s => {
  if (s.type !== 1) return false
  const name = s.name || s.key || ''
  return !LIVE_KEYWORDS.some(kw => name.includes(kw))
}))
const vodSiteOptions = computed(() => vodSites.value.map(s => ({ label: s.name, value: s.key })))
const hasSite = computed(() => vodSites.value.length > 0)

const interestTypes = [
  { key: 'dianshiju', name: '电视剧' },
  { key: 'dianying', name: '电影' },
  { key: 'zongyi', name: '综艺' },
  { key: 'donghua', name: '动漫' },
  { key: 'jilu', name: '纪录片' },
  { key: 'tiyu', name: '体育' },
]

const commonSites = computed(() => {
  if (!continueList.value.length) return []
  const keys = [...new Set(continueList.value.map((h: any) => h.site_key))]
  return vodSites.value.filter(s => keys.includes(s.key)).slice(0, 6)
})

function toggleInterest(key: string) {
  const idx = selectedInterests.value.indexOf(key)
  if (idx >= 0) selectedInterests.value.splice(idx, 1)
  else selectedInterests.value.push(key)
}

function applyInterests() {
  showColdStart.value = false
  localStorage.setItem('fongmi_interests', JSON.stringify(selectedInterests.value))
}

async function fetchSites() {
  const { getSites } = await import('@/api/config')
  const res: any = await getSites()
  allSites.value = res.data || []
}

async function loadContinueWatching() {
  try {
    const { historyAPI } = await import('@/api/vod')
    const res: any = await historyAPI.list(1, 20)
    // 空名字的条目渲染成空白卡（历史进度上报曾把元数据抹空），且无 site_key/vod_id/episode 时点击是死路径，一律不展示
    continueList.value = (res?.items || []).filter((h: any) =>
      h.name && ((h.site_key && h.vod_id) || h.episode))
    if (continueList.value.length === 0) {
      const saved = localStorage.getItem('fongmi_interests')
      showColdStart.value = !saved
    }
  } catch { continueList.value = [] } finally {
    nextTick().then(updateRailArrows)
  }
}

async function loadHot() {
  if (!selectedSite.value) return
  try {
    const { vodAPI } = await import('@/api/vod')
    const res: any = await vodAPI.home(selectedSite.value, true)
    hotVideos.value = res.list || []
  } catch { hotVideos.value = [] }
}

async function loadRecommendations() {
  try {
    const { historyAPI } = await import('@/api/vod')
    const res: any = await historyAPI.list(1, 10)
    const items = res?.items || []
    if (!items.length) return
    const siteKeys = [...new Set<string>(items.map((h: any) => h.site_key))].filter(Boolean)
    if (!siteKeys.length) return
    const result: any[] = []
    for (const sk of siteKeys.slice(0, 3)) {
      try {
        const { vodAPI } = await import('@/api/vod')
        const homeRes: any = await vodAPI.home(sk, true)
        const list = homeRes.list || []
        const site = allSites.value.find((s: any) => s.key === sk)
        const siteName = site?.name || sk
        list.slice(0, 12).forEach((v: any) => {
          v._site_key = sk
          v._site_name = siteName
          result.push(v)
        })
      } catch {}
    }
    recommendedVideos.value = result.slice(0, 18)
  } catch { recommendedVideos.value = [] } finally {
    nextTick().then(updateRailArrows)
  }
}

/** 拉取当前站点首页；返回是否拿到有效内容（用于坏源自动跳过） */
async function tryLoadHome(): Promise<boolean> {
  loading.value = true
  currentPage.value = 1
  try {
    const { vodAPI } = await import('@/api/vod')
    const res: any = await vodAPI.home(selectedSite.value, true)
    classes.value = res.class || []
    videos.value = res.list || []
    pagecount.value = res.pagecount || 1
    return videos.value.length > 0 || classes.value.length > 0
  } catch {
    return false
  } finally {
    loading.value = false
    nextTick().then(updateRailArrows)
  }
}

async function loadHome() {
  const ok = await tryLoadHome()
  if (!ok) window.$message?.error('加载首页失败')
}

function onSiteChange() {
  currentTid.value = ''
  currentCategoryName.value = ''
  currentPage.value = 1
  loadHot()
  loadHome()
}

async function onCategoryClick(tid: string, name: string) {
  currentTid.value = tid
  currentCategoryName.value = name
  currentPage.value = 1
  await loadCategory()
}

async function loadCategory() {
  loading.value = true
  currentPage.value = 1
  try {
    const { vodAPI } = await import('@/api/vod')
    const res: any = await vodAPI.category(selectedSite.value, currentTid.value, 1)
    let list: any[] = res.list || []
    pagecount.value = res.pagecount || 1
    // 部分源站父类过滤失效（父类 ID 查不到数据，内容都挂在子类下）：
    // 结果过少且存在子分类时，合并子分类首页内容兜底
    mergedCategory.value = false
    let children = classes.value.filter(c => String(c.type_pid || 0) === String(currentTid.value))
    if (!children.length) {
      // 源站 class 无 type_pid（平铺列表）时，按类型名推断同组子类
      const pat = siblingPattern(currentCategoryName.value)
      if (pat) children = classes.value.filter(c => pat(c.type_name) && String(c.type_id) !== String(currentTid.value))
    }
    if (list.length < 3 && children.length) {
      const childRes = await Promise.allSettled(
        children.slice(0, 12).map(c => vodAPI.category(selectedSite.value, c.type_id, 1))
      )
      const merged: any[] = [...list]
      const seen = new Set(list.map(v => String(v.vod_id)))
      for (const r of childRes) {
        if (r.status !== 'fulfilled') continue
        for (const v of ((r.value as any)?.list || [])) {
          const id = String(v.vod_id)
          if (seen.has(id)) continue
          seen.add(id)
          merged.push(v)
        }
      }
      if (merged.length > list.length) {
        list = merged.slice(0, 60)
        pagecount.value = 1
        mergedCategory.value = true
      }
    }
    videos.value = list
  } catch (e: any) {
    window.$message?.error('加载分类失败')
  } finally {
    loading.value = false
  }
}

const hasMore = computed(() => currentPage.value < pagecount.value)

/** 源站 class 为平铺列表（无 type_pid）时，按类型名推断主分类的同组子类 */
function siblingPattern(majorName: string): ((n: string) => boolean) | null {
  const name = majorName || ''
  if (name.includes('电影')) return n => n.endsWith('片')
  if (name.includes('电视剧')) return n => n.endsWith('剧')
  if (name.endsWith('剧')) return n => n.endsWith('剧')
  if (name.includes('综艺')) return n => n.includes('综艺')
  if (name.includes('动漫') || name.includes('动画')) return n => n.includes('动漫') || n.includes('动画')
  return null
}

let loadMoreObserver: IntersectionObserver | null = null
let lastFailAt = 0

watch(gridSentinel, (el) => {
  loadMoreObserver?.disconnect()
  loadMoreObserver = null
  if (el) {
    loadMoreObserver = new IntersectionObserver((entries) => {
      if (entries.some(e => e.isIntersecting)) loadMore()
    }, { rootMargin: '600px' })
    loadMoreObserver.observe(el)
  }
})

async function loadMore() {
  if (loading.value || loadingMore.value || !hasMore.value) return
  // 失败后 5 秒冷却，避免哨兵在视口内时密集重试
  if (Date.now() - lastFailAt < 5000) return
  loadingMore.value = true
  const reqSite = selectedSite.value
  const reqTid = currentTid.value
  try {
    const { vodAPI } = await import('@/api/vod')
    const next = currentPage.value + 1
    const res: any = await vodAPI.category(reqSite, reqTid, next)
    // 请求期间已切换站点/分类：丢弃过期响应
    if (selectedSite.value !== reqSite || currentTid.value !== reqTid) return
    const list: any[] = res.list || []
    if (!list.length) {
      if (res.pagecount == null) {
        // 无 pagecount：多为源站超时/失败，不封顶，冷却后滚动可重试
        lastFailAt = Date.now()
        return
      }
      // 源明确告知没有更多：封顶页码
      pagecount.value = Math.min(pagecount.value, currentPage.value)
      return
    }
    pagecount.value = res.pagecount || pagecount.value
    const seen = new Set(videos.value.map(v => String(v.vod_id)))
    const fresh = list.filter((v: any) => {
      const id = String(v.vod_id)
      if (seen.has(id)) return false
      seen.add(id)
      return true
    })
    currentPage.value = next
    if (fresh.length) videos.value = [...videos.value, ...fresh]
  } catch (e: any) {
    lastFailAt = Date.now()
    window.$message?.error('加载更多失败')
  } finally {
    loadingMore.value = false
    // 哨兵仍在视口内（内容未铺满一屏）时继续补载下一页
    await nextTick()
    if (hasMore.value && gridSentinel.value && loadMoreObserver) {
      loadMoreObserver.unobserve(gridSentinel.value)
      loadMoreObserver.observe(gridSentinel.value)
    }
  }
}

function goDetail(id: string, siteKey?: string) {
  openPlayPage({ path: `/detail/${siteKey || selectedSite.value}/${id}`, query: { autoplay: '1' } }, 'vod')
}

function goContinue(item: any) {
  if (item.site_key && item.vod_id) {
    openPlayPage({ path: `/detail/${item.site_key}/${item.vod_id}`, query: { autoplay: '1' } }, 'vod')
  } else if (item.episode) {
    openPlayPage({ path: '/play', query: { url: item.episode } }, 'vod')
  }
}

/** 历史里的 episode 可能是「第01集」这类名称，也可能是播放地址（老数据），地址不展示 */
function episodeLabel(ep?: string): string {
  if (!ep) return ''
  if (/^https?:\/\//i.test(ep)) return ''
  return ep
}

// ---------- 横向 Rail 交互（滚轮转换 + 箭头） ----------
/** 鼠标滚轮默认只能纵向滚页面；悬停在横条上时把纵向滚轮转成横向滚动，
 *  到达边界时不拦截，页面继续正常纵向滚动 */
function onRailWheel(e: WheelEvent) {
  const el = e.currentTarget as HTMLElement
  const max = el.scrollWidth - el.clientWidth
  if (max <= 0) return
  const delta = Math.abs(e.deltaY) >= Math.abs(e.deltaX) ? e.deltaY : e.deltaX
  if ((delta > 0 && el.scrollLeft >= max - 1) || (delta < 0 && el.scrollLeft <= 1)) return
  e.preventDefault()
  el.scrollLeft += delta
}

function scrollRail(e: MouseEvent, dir: number) {
  const wrap = (e.currentTarget as HTMLElement).closest('.rail-wrap')
  const sc = wrap?.querySelector('.rail-scroll') as HTMLElement | null
  if (!sc) return
  sc.scrollLeft += dir * sc.clientWidth * 0.8
}

/** 内容不足以横向滚动时隐藏箭头 */
function updateRailArrows() {
  document.querySelectorAll('.rail-wrap').forEach(w => {
    const sc = w.querySelector('.rail-scroll')
    if (sc) w.toggleAttribute('data-scrollable', sc.scrollWidth > sc.clientWidth + 4)
  })
}

function switchSite(key: string) {
  selectedSite.value = key
  currentTid.value = ''
  currentPage.value = 1
  loadHot()
  loadHome()
}

async function importDemoSource() {
  importingDemo.value = true
  try {
    const { importConfig } = await import('@/api/config')
    await importConfig({ url: 'https://raw.githubusercontent.com/fongmi/sub/main/demo.json', type: 'vod' })
    window.$message?.success('示例源导入成功，请刷新页面')
    showGuide.value = false
    setTimeout(() => location.reload(), 1500)
  } catch (e: any) {
    window.$message?.error('导入失败: ' + (e?.message || ''))
  } finally {
    importingDemo.value = false
  }
}

const LAST_SITE_KEY = 'fongmi_last_site'

// 记住上次选中的站点，下次进入优先恢复；已失效则回退第一个
function pickInitialSite(): string {
  let saved = ''
  try { saved = localStorage.getItem(LAST_SITE_KEY) || '' } catch {}
  return vodSites.value.find(s => s.key === saved)?.key || vodSites.value[0].key
}

watch(selectedSite, (k) => {
  if (!k) return
  try { localStorage.setItem(LAST_SITE_KEY, k) } catch {}
})

onMounted(async () => {
  window.addEventListener('resize', updateRailArrows)
  await fetchSites()
  if (vodSites.value.length > 0) {
    selectedSite.value = pickInitialSite()
    // 首选站点无内容（源超时/失效）时自动尝试下一个，直到拿到内容
    if (!(await tryLoadHome())) {
      for (const s of vodSites.value) {
        if (s.key === selectedSite.value) continue
        selectedSite.value = s.key
        if (await tryLoadHome()) break
      }
    }
    await Promise.all([
      loadContinueWatching(),
      loadHot(),
    ])
    // 猜你喜欢需要串行拉多个站点，不阻塞首屏渲染
    loadRecommendations()
  }
  initLoading.value = false
  nextTick().then(updateRailArrows)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', updateRailArrows)
  loadMoreObserver?.disconnect()
  loadMoreObserver = null
})
</script>

<style scoped>
.home-page { padding: 20px; max-width: 1600px; margin: 0 auto; min-height: 100vh; }
.init-loading { display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 50vh; }
.empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 50vh; text-align: center; }
.empty-icon { margin-bottom: 16px; }
.empty-state h2 { font-size: 28px; margin: 0 0 8px; }
.empty-state p { font-size: 16px; color: #888; margin: 0 0 24px; }

.guide-steps { display: flex; flex-direction: column; gap: 16px; }
.guide-step { display: flex; gap: 12px; align-items: flex-start; }
.step-num { width: 28px; height: 28px; border-radius: 50%; background: var(--n-primary-color); color: #fff; display: flex; align-items: center; justify-content: center; font-size: 14px; font-weight: 600; flex-shrink: 0; }
.step-title { font-size: 15px; font-weight: 500; margin-bottom: 2px; }
.step-desc { font-size: 13px; color: #888; }

.home-section { margin-bottom: 28px; }
.section-header { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.section-header h3 { font-size: 18px; font-weight: 600; margin: 0; flex-shrink: 0; }
.section-more { font-size: 13px; color: var(--n-primary-color); cursor: pointer; flex-shrink: 0; }

.rail-scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; scrollbar-width: none; }
.rail-scroll::-webkit-scrollbar { display: none; }
.rail-track { display: flex; gap: 12px; padding-bottom: 4px; }
.rail-card { flex-shrink: 0; width: 160px; cursor: pointer; border-radius: 10px; overflow: hidden; background: var(--n-card-color); transition: all 0.2s; }
.rail-card:hover { transform: translateY(-2px); box-shadow: 0 4px 16px rgba(0,0,0,0.15); }

.rail-wrap { position: relative; }
.rail-arrow {
  position: absolute; top: 42%; transform: translateY(-50%); z-index: 6;
  width: 34px; height: 34px; border-radius: 50%; border: 1px solid rgba(255,255,255,0.2);
  background: rgba(0,0,0,0.55); color: #fff; cursor: pointer;
  display: none; align-items: center; justify-content: center;
  transition: background 0.2s; backdrop-filter: blur(4px);
}
.rail-wrap[data-scrollable]:hover .rail-arrow { display: flex; }
.rail-arrow.left { left: -10px; }
.rail-arrow.right { right: -10px; }
.rail-arrow:hover { background: rgba(0,170,238,0.85); border-color: transparent; }
.rail-cover { position: relative; aspect-ratio: 2/3; overflow: hidden; background: #1a1a2e; }
.rail-cover img { width: 100%; height: 100%; object-fit: cover; transition: transform 0.3s; }
.rail-card:hover .rail-cover img { transform: scale(1.05); }
.cover-badge { position: absolute; top: 8px; right: 8px; background: rgba(255,80,80,0.9); color: #fff; font-size: 11px; padding: 2px 6px; border-radius: 4px; font-weight: 500; }
.cover-overlay { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; background: rgba(0,0,0,0.4); opacity: 0; transition: opacity 0.3s; }
.rail-card:hover .cover-overlay { opacity: 1; }
.play-icon { width: 40px; height: 40px; background: rgba(255,255,255,0.9); border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 16px; color: #333; padding-left: 3px; }
.rail-info { padding: 8px 10px; }
.rail-name { font-size: 13px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-bottom: 2px; }
.rail-meta { font-size: 11px; color: #888; }

.continue-card .rail-cover { aspect-ratio: 16/9; }
.continue-progress { position: absolute; bottom: 0; left: 0; right: 0; height: 3px; background: rgba(255,255,255,0.15); }
.progress-fill { height: 100%; background: var(--n-primary-color); transition: width 0.3s; }

.cold-start { background: var(--n-card-color); border-radius: 12px; padding: 16px 20px; }
.interest-grid { display: flex; flex-wrap: wrap; gap: 8px; }
.interest-btn { padding: 8px 20px; border: 1px solid rgba(255,255,255,0.15); border-radius: 20px; background: transparent; cursor: pointer; font-size: 13px; color: #ccc; transition: all 0.2s; }
.interest-btn:hover { border-color: var(--n-primary-color); color: #fff; }
.interest-btn.active { background: var(--n-primary-color); border-color: var(--n-primary-color); color: #fff; }

.site-select-mini { margin-left: auto; }
.class-tabs-mini { flex: 1; min-width: 0; display: flex; gap: 6px; overflow-x: auto; -webkit-overflow-scrolling: touch; }
.class-tab { flex-shrink: 0; padding: 4px 14px; border: 1px solid rgba(255,255,255,0.12); border-radius: 16px; background: transparent; cursor: pointer; font-size: 12px; color: #aaa; transition: all 0.2s; white-space: nowrap; }
.class-tab:hover { border-color: var(--n-primary-color); color: #fff; }
.class-tab.active { background: var(--n-primary-color); border-color: var(--n-primary-color); color: #fff; }

.source-chips { display: flex; gap: 8px; flex-wrap: wrap; }
.source-chip { padding: 6px 16px; border: 1px solid rgba(255,255,255,0.12); border-radius: 16px; background: transparent; cursor: pointer; font-size: 13px; color: #aaa; transition: all 0.2s; }
.source-chip:hover { border-color: var(--n-primary-color); color: #fff; background: rgba(0,170,238,0.08); }

.skeleton-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 12px; }
.skeleton-card { border-radius: 10px; overflow: hidden; }
.video-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 12px; }
.video-card { border-radius: 10px; overflow: hidden; background: var(--n-card-color); cursor: pointer; transition: all 0.3s; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.video-card:hover { transform: translateY(-4px); box-shadow: 0 8px 24px rgba(0,0,0,0.15); }
.card-cover { position: relative; aspect-ratio: 2/3; overflow: hidden; background: #1a1a2e; }
.card-cover img { width: 100%; height: 100%; object-fit: cover; transition: transform 0.3s; }
.video-card:hover .card-cover img { transform: scale(1.05); }
.card-info { padding: 8px 10px; }
.video-name { font-size: 13px; font-weight: 500; line-height: 1.4; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; margin-bottom: 4px; }
.video-meta { display: flex; gap: 4px; flex-wrap: wrap; }
.meta-tag { font-size: 10px; color: #888; background: var(--n-divider-color); padding: 1px 6px; border-radius: 3px; }
.no-data { display: flex; justify-content: center; padding: 40px 0; color: #888; }
.load-more-sentinel { display: flex; justify-content: center; align-items: center; min-height: 48px; padding: 8px 0; }
.no-more-tip { text-align: center; color: #666; font-size: 12px; padding: 12px 0; }
</style>