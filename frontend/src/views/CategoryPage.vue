<template>
  <div class="category-page">
    <div class="cat-header">
      <n-button text @click="$router.back()">← 返回</n-button>
      <h2>{{ typeName || '全部分类' }}</h2>
    </div>
    <n-spin :show="loading">
      <div v-if="!loading && !videos.length" class="empty"><n-empty description="暂无数据" /></div>
      <div class="video-grid">
        <div v-for="video in videos" :key="video.vod_id" class="video-card" @click="goDetail(video.vod_id)">
          <div class="card-cover">
            <img :src="imgUrl(video.vod_pic, video.vod_name) || defaultPic" loading="lazy" />
            <div v-if="video.vod_remarks" class="cover-badge">{{ video.vod_remarks }}</div>
            <div class="cover-overlay"><span class="play-icon">▶</span></div>
          </div>
          <div class="card-info"><div class="video-name">{{ video.vod_name }}</div></div>
        </div>
      </div>
    </n-spin>
    <div v-if="pagecount > 1" class="pagination">
      <n-pagination v-model:page="currentPg" :page-count="pagecount" @update:page="loadPage" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { NButton, NSpin, NEmpty, NPagination } from 'naive-ui'
import { imgUrl } from '@/api/img'
import { openInNewTab } from '@/utils/navigation'

const route = useRoute()
const siteKey = ref('')
const tid = ref('')
const typeName = ref('')
const loading = ref(false)
const videos = ref<any[]>([])
const currentPg = ref(1)
const pagecount = ref(1)
const defaultPic = imgUrl('')

onMounted(async () => {
  siteKey.value = route.params.site as string
  tid.value = route.query.tid as string || ''
  await loadPage(1)
})

async function loadPage(pg: number) {
  currentPg.value = pg
  loading.value = true
  try {
    const { vodAPI } = await import('@/api/vod')
    const res: any = await vodAPI.category(siteKey.value, tid.value, pg)
    videos.value = res.list || []
    pagecount.value = res.pagecount || 1
  } finally {
    loading.value = false
  }
}

function goDetail(id: string) {
  openInNewTab({ path: `/detail/${siteKey.value}/${id}`, query: { autoplay: '1' } })
}
</script>

<style scoped>
.category-page { padding: 20px; max-width: 1600px; margin: 0 auto; }
.cat-header { display: flex; align-items: center; gap: 12px; margin-bottom: 20px; }
.cat-header h2 { margin: 0; flex: 1; }
.empty { padding: 60px 0; display: flex; justify-content: center; }
.video-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 16px; }
.pagination { display: flex; justify-content: center; margin-top: 24px; }
.video-card { border-radius: 12px; overflow: hidden; background: var(--n-card-color); cursor: pointer; transition: all 0.3s; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.video-card:hover { transform: translateY(-4px); box-shadow: 0 8px 24px rgba(0,0,0,0.15); }
.card-cover { position: relative; aspect-ratio: 2/3; background: #1a1a2e; }
.card-cover img { width: 100%; height: 100%; object-fit: cover; }
.cover-badge { position: absolute; top: 8px; right: 8px; background: rgba(255,80,80,0.9); color: #fff; font-size: 11px; padding: 2px 6px; border-radius: 4px; }
.cover-overlay { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; background: rgba(0,0,0,0.4); opacity: 0; transition: opacity 0.3s; }
.video-card:hover .cover-overlay { opacity: 1; }
.play-icon { width: 48px; height: 48px; background: rgba(255,255,255,0.9); border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 20px; color: #333; padding-left: 4px; }
.card-info { padding: 10px 12px; }
.video-name { font-size: 13px; font-weight: 500; text-overflow: ellipsis; overflow: hidden; white-space: nowrap; }
</style>
