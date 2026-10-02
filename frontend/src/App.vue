<template>
  <n-config-provider :theme="currentTheme">
    <n-message-provider>
      <n-layout position="absolute">
        <n-layout-header bordered class="app-header">
          <div class="header-content">
            <div class="logo" @click="$router.push('/')">FongMi TV</div>
            <nav class="nav-links">
              <router-link to="/">首页</router-link>
              <router-link to="/live">直播</router-link>
              <router-link to="/local">本地</router-link>
              <router-link to="/history">我的</router-link>
              <router-link to="/setting">设置</router-link>
            </nav>
            <div class="header-search">
              <n-input
                v-model:value="searchKeyword"
                placeholder="搜索视频..."
                size="small"
                round
                clearable
                @keyup.enter="doSearch"
              >
                <template #prefix>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:-2px">
                    <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>
                  </svg>
                </template>
              </n-input>
            </div>
            <button class="theme-toggle" @click="toggleTheme" :title="isDark ? '切换亮色模式' : '切换暗色模式'">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path v-if="isDark" d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
                <circle v-else cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>
              </svg>
            </button>
          </div>
        </n-layout-header>
        <n-layout-content content-style="padding: 0;">
          <router-view v-slot="{ Component }">
            <!-- :duration 让过渡按定时器收尾，窗口被遮挡/帧冻结时导航不再卡死 -->
            <transition name="page-fade" mode="out-in" :duration="{ enter: 250, leave: 250 }">
              <component :is="Component" />
            </transition>
          </router-view>
        </n-layout-content>
      </n-layout>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { NConfigProvider, NMessageProvider, NLayout, NLayoutHeader, NLayoutContent, NInput, darkTheme } from 'naive-ui'

const router = useRouter()
const searchKeyword = ref('')
const isDark = ref(true)
const THEME_KEY = 'fongmi_theme'

try {
  const saved = localStorage.getItem(THEME_KEY)
  if (saved === 'light') isDark.value = false
  else if (saved === 'dark') isDark.value = true
} catch { isDark.value = true }

const currentTheme = computed(() => isDark.value ? darkTheme : null)

function toggleTheme() {
  isDark.value = !isDark.value
  try { localStorage.setItem(THEME_KEY, isDark.value ? 'dark' : 'light') } catch {}
  document.documentElement.setAttribute('data-theme', isDark.value ? 'dark' : 'light')
}

function doSearch() {
  if (!searchKeyword.value.trim()) return
  router.push({ path: '/search', query: { wd: searchKeyword.value } })
}

document.documentElement.setAttribute('data-theme', isDark.value ? 'dark' : 'light')
</script>

<style>
:root { --bg-color: #0f0f13; --text-color: #e0e0e0; --card-bg: #1a1a2e; --border-color: rgba(255,255,255,0.06); --n-primary-color: #00aaee; }
[data-theme="light"] { --bg-color: #f5f5f5; --text-color: #333; --card-bg: #fff; --border-color: rgba(0,0,0,0.08); }

* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: var(--bg-color); color: var(--text-color); }
a { text-decoration: none; color: inherit; }

.app-header { height: 56px; display: flex; align-items: center; background: var(--card-bg); backdrop-filter: blur(10px); border-bottom: 1px solid var(--border-color); }
.header-content { max-width: 1600px; width: 100%; margin: 0 auto; padding: 0 20px; display: flex; align-items: center; gap: 24px; }
.logo { font-size: 20px; font-weight: 700; cursor: pointer; display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.nav-links { display: flex; gap: 4px; }
.nav-links a { font-size: 14px; color: #888; transition: all 0.2s; padding: 6px 14px; border-radius: 6px; }
.nav-links a:hover, .nav-links a.router-link-active { color: var(--text-color); background: rgba(128,128,128,0.1); }
.header-search { margin-left: auto; width: 240px; }
.theme-toggle { background: none; border: none; color: #888; cursor: pointer; padding: 6px; border-radius: 6px; transition: all 0.2s; }
.theme-toggle:hover { color: var(--text-color); background: rgba(128,128,128,0.1); }

.page-fade-enter-active, .page-fade-leave-active { transition: opacity 0.2s ease, transform 0.2s ease; }
.page-fade-enter-from { opacity: 0; transform: translateY(6px); }
.page-fade-leave-to { opacity: 0; transform: translateY(-6px); }
@media (prefers-reduced-motion: reduce) {
  .page-fade-enter-active, .page-fade-leave-active { transition: none; }
}

:focus-visible { outline: 2px solid var(--n-primary-color, #4098ff); outline-offset: 2px; }
</style>