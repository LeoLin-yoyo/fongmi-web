<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-logo">FongMi TV</div>
      <div class="login-sub">请输入账号密码以继续</div>
      <n-form @submit.prevent="doLogin">
        <n-input
          v-model:value="username"
          placeholder="账号"
          size="large"
          class="login-input"
          @keyup.enter="doLogin"
        >
          <template #prefix>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="8" r="4"/><path d="M4 21v-1a6 6 0 0 1 12 0v1"/></svg>
          </template>
        </n-input>
        <n-input
          v-model:value="password"
          type="password"
          show-password-on="click"
          placeholder="密码"
          size="large"
          class="login-input"
          @keyup.enter="doLogin"
        >
          <template #prefix>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
          </template>
        </n-input>
        <n-button
          type="primary"
          size="large"
          block
          :loading="loading"
          :disabled="!username.trim() || !password"
          @click="doLogin"
        >
          登录
        </n-button>
      </n-form>
      <div v-if="error" class="login-error">{{ error }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NInput, NButton, NForm } from 'naive-ui'
import { authAPI } from '@/api/auth'

const router = useRouter()
const username = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')

async function doLogin() {
  if (!username.value.trim() || !password.value) return
  loading.value = true
  error.value = ''
  try {
    await authAPI.login(username.value.trim(), password.value)
    const redirect = new URLSearchParams(window.location.search).get('redirect')
    router.replace(redirect && redirect.startsWith('/') ? redirect : '/')
  } catch (e: any) {
    const status = e?.response?.status
    if (status === 429) error.value = e?.response?.data?.detail || '尝试过于频繁，请稍后重试'
    else error.value = e?.response?.data?.detail || '账号或密码错误'
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  // 已登录或无需登录时，直接放行
  try {
    const res: any = await authAPI.status()
    if (!res.data?.required || res.data?.authenticated) router.replace('/')
  } catch { /* ignore */ }
})
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background: var(--bg-color, #0f0f13);
}
.login-card {
  width: 100%;
  max-width: 360px;
  padding: 36px 32px;
  border-radius: 16px;
  background: var(--card-bg, #1a1a2e);
  border: 1px solid rgba(128, 128, 128, 0.15);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.25);
}
.login-logo {
  font-size: 24px;
  font-weight: 700;
  text-align: center;
  letter-spacing: 0.5px;
}
.login-sub {
  font-size: 13px;
  color: #888;
  text-align: center;
  margin: 8px 0 24px;
}
.login-input {
  margin-bottom: 14px;
}
.login-error {
  margin-top: 14px;
  font-size: 13px;
  color: #e88080;
  text-align: center;
}
</style>
