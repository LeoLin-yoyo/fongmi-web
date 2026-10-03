<template>
  <div class="search-page">
    <div class="search-header">
      <n-input
        v-model:value="keyword"
        placeholder="输入关键词搜索..."
        class="search-input"
        round
        autofocus
        clearable
        @keyup.enter="doSearch"
      >
        <template #prefix>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>
          </svg>
        </template>
      </n-input>

      <div v-if="!searched" class="search-hints">
        <div v-if="searchHistory.length" class="hint-section">
          <div class="hint-header">
            <span>搜索历史</span>
            <button class="hint-clear" @click="clearHistory">清空</button>
          </div>
          <div class="hint-tags">
            <button v-for="h in searchHistory" :key="h" class="hint-tag" @click="clickHistory(h)">{{ h }}</button>
          </div>
        </div>
        <div class="hint-section">
          <div class="hint-header"><span>热搜推荐</span></div>
          <div class="hint-tags">
            <button v-for="h in hotSearches" :key="h" class="hint-tag hot" @click="clickHistory(h)">{{ h }}</button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="loading" class="loading-area">
      <n-spin size="large" />
    </div>

    <template v-else-if="searched && hasData">
      <div class="search-toolbar">
        <div class="filter-group">
          <n-select v-model:value="filterType" :options="typeOptions" placeholder="类型" clearable style="width:100px" size="small" />
          <n-input v-model:value="filterYear" placeholder="年份" style="width:80px" size="small" clearable />
          <n-select v-model:value="filterArea" :options="areaOptions" placeholder="地区" clearable style="width:100px" size="small" />
          <n-select v-model:value="sortBy" :options="sortOptions" placeholder="排序" style="width:100px" size="small" />
          <n-button-group size="small">
            <n-button :type="viewMode === 'merged' ? 'primary' : 'default'" @click="viewMode = 'merged'">合并</n-button>
            <n-button :type="viewMode === 'expanded' ? 'primary' : 'default'" @click="viewMode = 'expanded'">展开</n-button>
          </n-button-group>
        </div>
        <div class="result-count">共 {{ activeTab === '__all__' ? (viewMode === 'merged' ? mergedGroups.length : filteredResults.length) : (perSite[activeTab]?.results.length || 0) }} 个结果</div>
      </div>

      <div class="search-layout">
        <div class="site-tabs">
          <div class="tab-item" :class="{ active: activeTab === '__all__' }" @click="activeTab = '__all__'">
            <span class="tab-name">全部</span>
            <span class="tab-count">{{ filteredResults.length }}</span>
          </div>
          <div v-for="(info, sKey) in visibleSites" :key="sKey" class="tab-item" :class="{ active: activeTab === sKey }" @click="activeTab = sKey">
            <span class="tab-name">{{ info.name }}</span>
            <span class="tab-count">{{ info.results.length }}</span>
          </div>
        </div>
        <div class="tab-content">
          <!-- 全部 tab：合并视图按片名聚合，展开视图平铺 -->
          <div v-if="activeTab === '__all__' && viewMode === 'merged'" class="results-grid">
            <div v-for="g in mergedGroups" :key="'grp_' + g.key" class="video-card" @click="goDetail(g.items[0])">
              <div class="card-cover">
                <img :src="imgUrl(g.items[0].vod_pic, g.items[0].vod_name) || defaultPic" loading="lazy" />
                <div v-if="g.items[0].vod_remarks" class="cover-badge">{{ g.items[0].vod_remarks }}</div>
                <div v-if="g.items.length > 1" class="site-count-badge">{{ g.items.length }}源</div>
              </div>
              <div class="card-info">
                <div class="video-name">{{ g.name }}</div>
                <div class="video-meta">
                  <span v-if="g.items[0].vod_year" class="meta-tag">{{ g.items[0].vod_year }}</span>
                  <span v-if="g.items[0].vod_area" class="meta-tag">{{ g.items[0].vod_area }}</span>
                </div>
                <div class="video-site" v-if="g.items.length > 1">{{ g.sites.join(' / ') }}</div>
                <div class="video-site" v-else-if="g.items[0]._site_name">{{ g.items[0]._site_name }}</div>
              </div>
            </div>
          </div>
          <div v-else-if="activeTab === '__all__'" class="results-grid">
            <div v-for="v in filteredResults" :key="'all_' + v._site_key + '_' + v.vod_id" class="video-card" @click="goDetail(v)">
              <div class="card-cover">
                <img :src="imgUrl(v.vod_pic, v.vod_name) || defaultPic" loading="lazy" />
                <div v-if="v.vod_remarks" class="cover-badge">{{ v.vod_remarks }}</div>
              </div>
              <div class="card-info">
                <div class="video-name">{{ v.vod_name }}</div>
                <div class="video-meta">
                  <span v-if="v.vod_year" class="meta-tag">{{ v.vod_year }}</span>
                  <span v-if="v.vod_area" class="meta-tag">{{ v.vod_area }}</span>
                </div>
                <div class="video-site" v-if="v._site_name">{{ v._site_name }}</div>
              </div>
            </div>
          </div>
          <div v-else class="results-grid">
            <div v-for="v in (perSite[activeTab]?.results || [])" :key="activeTab + '_' + v.vod_id" class="video-card" @click="goDetail(v)">
              <div class="card-cover">
                <img :src="imgUrl(v.vod_pic, v.vod_name) || defaultPic" loading="lazy" />
                <div v-if="v.vod_remarks" class="cover-badge">{{ v.vod_remarks }}</div>
              </div>
              <div class="card-info">
                <div class="video-name">{{ v.vod_name }}</div>
                <div class="video-meta">
                  <span v-if="v.vod_year" class="meta-tag">{{ v.vod_year }}</span>
                  <span v-if="v.vod_area" class="meta-tag">{{ v.vod_area }}</span>
                </div>
                <div class="video-site" v-if="v._site_name">{{ v._site_name }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <div v-else-if="searched" class="no-result"><n-empty description="未找到相关结果" /></div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NInput, NEmpty, NSpin, NSelect, NButton, NButtonGroup } from 'naive-ui'
import { imgUrl } from '@/api/img'
import { openInNewTab } from '@/utils/navigation'

const route = useRoute()
const router = useRouter()
const keyword = ref((route.query.wd as string) || '')
const loading = ref(false)
const searched = ref(false)
const searchData = ref<any>({ merged: [], per_site: {} })
const activeTab = ref('__all__')
const searchHistory = ref<string[]>([])
const filterType = ref<string | null>(null)
const filterYear = ref('')
const filterArea = ref<string | null>(null)
const sortBy = ref<string | null>(null)
const viewMode = ref<'merged' | 'expanded'>('merged')

const HOT_SEARCHES = ['最新电影', '热门电视剧', '动漫', '综艺', '纪录片']
const HISTORY_KEY = 'fongmi_search_history'

const typeOptions = [
  { label: '电影', value: '电影' },
  { label: '电视剧', value: '电视剧' },
  { label: '综艺', value: '综艺' },
  { label: '动漫', value: '动漫' },
  { label: '纪录片', value: '纪录片' },
]

const areaOptions = [
  { label: '大陆', value: '大陆' },
  { label: '香港', value: '香港' },
  { label: '台湾', value: '台湾' },
  { label: '美国', value: '美国' },
  { label: '韩国', value: '韩国' },
  { label: '日本', value: '日本' },
  { label: '英国', value: '英国' },
  { label: '泰国', value: '泰国' },
]

const sortOptions = [
  { label: '默认', value: '' },
  { label: '年份 ↑', value: 'year_asc' },
  { label: '年份 ↓', value: 'year_desc' },
  { label: '名称', value: 'name' },
]

const mergedResults = computed(() => searchData.value.merged || [])
const perSite = computed(() => searchData.value.per_site || {})
const hasData = computed(() => mergedResults.value.length > 0 || Object.keys(perSite.value).length > 0)

/** 右侧源列表只显示有命中的站点（全站并发搜索会给 0 结果/失败的站点也建条目，一千多个 0 没有展示意义） */
const visibleSites = computed(() => {
  const out: Record<string, { name: string; results: any[] }> = {}
  for (const [key, info] of Object.entries(perSite.value) as [string, any][]) {
    if (info?.results?.length) out[key] = { name: info.name, results: info.results }
  }
  return out
})

const filteredResults = computed(() => {
  let list = [...mergedResults.value]
  if (filterType.value) {
    list = list.filter(v => (v.vod_type || '').includes(filterType.value!))
  }
  if (filterYear.value) {
    list = list.filter(v => (v.vod_year || '').includes(filterYear.value))
  }
  if (filterArea.value) {
    list = list.filter(v => (v.vod_area || '').includes(filterArea.value!))
  }
  if (sortBy.value) {
    switch (sortBy.value) {
      case 'year_asc':
        list.sort((a, b) => (a.vod_year || '').localeCompare(b.vod_year || ''))
        break
      case 'year_desc':
        list.sort((a, b) => (b.vod_year || '').localeCompare(a.vod_year || ''))
        break
      case 'name':
        list.sort((a, b) => (a.vod_name || '').localeCompare(b.vod_name || ''))
        break
    }
  }
  return list
})

/** 合并视图：按片名（去标点归一）聚合，同名不同站归为一组，年版/年份不同的仍分开（T5-2） */
const mergedGroups = computed(() => {
  const map = new Map<string, { key: string; name: string; items: any[]; sites: string[] }>()
  for (const v of filteredResults.value) {
    const name = (v.vod_name || '').trim()
    if (!name) continue
    const norm = name.replace(/[\s\W_]+/g, '').toLowerCase() + '|' + (v.vod_year || '')
    let g = map.get(norm)
    if (!g) {
      g = { key: norm, name, items: [], sites: [] }
      map.set(norm, g)
    }
    g.items.push(v)
    if (v._site_name && !g.sites.includes(v._site_name)) g.sites.push(v._site_name)
  }
  return [...map.values()].sort((a, b) => b.items.length - a.items.length)
})

const hotSearches = computed(() => {
  return [...new Set([...HOT_SEARCHES, ...searchHistory.value])].slice(0, 8)
})

const defaultPic = imgUrl('')

function loadHistory() {
  try {
    const saved = localStorage.getItem(HISTORY_KEY)
    searchHistory.value = saved ? JSON.parse(saved) : []
  } catch { searchHistory.value = [] }
}

function saveHistory(kw: string) {
  const list = [kw, ...searchHistory.value.filter(h => h !== kw)].slice(0, 10)
  searchHistory.value = list
  localStorage.setItem(HISTORY_KEY, JSON.stringify(list))
}

function clearHistory() {
  searchHistory.value = []
  localStorage.removeItem(HISTORY_KEY)
}

function clickHistory(kw: string) {
  keyword.value = kw
  doSearch()
}

onMounted(async () => {
  loadHistory()
  if (keyword.value) await doSearch()
})

async function doSearch() {
  if (!keyword.value.trim()) return
  loading.value = true
  searched.value = true
  activeTab.value = '__all__'
  saveHistory(keyword.value.trim())
  // 同步到 URL，热搜/历史点击可跳转分享
  router.replace({ query: { wd: keyword.value.trim() } }).catch(() => {})
  try {
    const { vodAPI } = await import('@/api/vod')
    const res: any = await vodAPI.searchAggregated(keyword.value)
    searchData.value = res || { merged: [], per_site: {} }
  } catch (e: any) {
    window.$message?.error('搜索失败')
    searchData.value = { merged: [], per_site: {} }
  } finally {
    loading.value = false
  }
}

function goDetail(v: any) {
  const siteKey = v._site_key
  const vodId = v.vod_id
  if (siteKey && vodId) {
    openInNewTab({ path: `/detail/${siteKey}/${vodId}`, query: { autoplay: '1' } })
  }
}
</script>

<style scoped>
.search-page { padding: 20px; max-width: 1600px; margin: 0 auto; }
.search-input { margin-bottom: 12px; max-width: 600px; }
.loading-area { display: flex; justify-content: center; padding: 60px 0; }

.search-hints { margin-bottom: 20px; }
.hint-section { margin-bottom: 16px; }
.hint-header { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; font-size: 13px; color: #888; }
.hint-clear { background: none; border: none; color: var(--n-primary-color); cursor: pointer; font-size: 12px; }
.hint-tags { display: flex; flex-wrap: wrap; gap: 8px; }
.hint-tag { padding: 6px 14px; border: 1px solid rgba(255,255,255,0.12); border-radius: 16px; background: transparent; cursor: pointer; font-size: 12px; color: #aaa; transition: all 0.2s; }
.hint-tag:hover { border-color: var(--n-primary-color); color: #fff; }
.hint-tag.hot { color: #ff6b6b; border-color: rgba(255,107,107,0.3); }

.search-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.filter-group { display: flex; gap: 8px; align-items: center; }
.result-count { font-size: 13px; color: #888; margin-left: auto; }

.search-layout { display: flex; gap: 16px; min-height: 60vh; }
.site-tabs { width: 140px; flex-shrink: 0; display: flex; flex-direction: column; gap: 4px; position: sticky; top: 76px; align-self: flex-start; max-height: calc(100vh - 100px); overflow-y: auto; -webkit-overflow-scrolling: touch; }
.tab-item { display: flex; align-items: center; justify-content: space-between; padding: 10px 14px; border-radius: 8px; cursor: pointer; transition: all 0.2s; font-size: 13px; color: #888; background: transparent; }
.tab-item:hover { background: rgba(255,255,255,0.05); color: #ccc; }
.tab-item.active { background: rgba(64,128,255,0.15); color: #4098ff; font-weight: 600; }
.tab-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.tab-count { font-size: 11px; background: rgba(255,255,255,0.08); border-radius: 10px; padding: 1px 7px; margin-left: 8px; flex-shrink: 0; }
.tab-content { flex: 1; min-width: 0; }
.results-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 16px; }
.no-result { padding: 60px 0; display: flex; justify-content: center; }

.video-card { border-radius: 12px; overflow: hidden; background: var(--n-card-color); cursor: pointer; transition: all 0.3s; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.video-card:hover { transform: translateY(-4px); box-shadow: 0 8px 24px rgba(0,0,0,0.15); }
.card-cover { position: relative; aspect-ratio: 2/3; background: #1a1a2e; }
.card-cover img { width: 100%; height: 100%; object-fit: cover; }
.cover-badge { position: absolute; top: 8px; right: 8px; background: rgba(255,80,80,0.9); color: #fff; font-size: 11px; padding: 2px 6px; border-radius: 4px; }
.site-count-badge { position: absolute; top: 8px; left: 8px; background: rgba(0,170,238,0.9); color: #fff; font-size: 11px; padding: 2px 6px; border-radius: 4px; font-weight: 500; }
.card-info { padding: 10px 12px; }
.video-name { font-size: 13px; font-weight: 500; text-overflow: ellipsis; overflow: hidden; white-space: nowrap; }
.video-meta { display: flex; gap: 4px; margin-top: 2px; }
.meta-tag { font-size: 10px; color: #888; background: var(--n-divider-color); padding: 1px 6px; border-radius: 3px; }
.video-site { font-size: 11px; color: #888; margin-top: 2px; }
</style>