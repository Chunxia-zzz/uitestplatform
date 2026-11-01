<script setup lang="ts">
/**
 * 报告页（M3.2 / GAP-27）。
 *
 * HTML 报告用 iframe 内嵌（保持"报告就是一份可离线保存的 HTML"这个事实），
 * JSON 视图给机器读 / 排查用。二者都走同一个 `/executions/{id}/report` 端点。
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { executionReportUrl, getExecution } from '@/api'
import type { Execution } from '@/api/types'
import { toastError, toastSuccess } from '@/components/AppToast'

const route = useRoute()
const router = useRouter()

const executionId = computed(() => Number(route.params.id))
const format = ref<'html' | 'json'>('html')
const execution = ref<Execution | null>(null)
const jsonText = ref('')
const loading = ref(false)
const jsonError = ref('')

const htmlUrl = computed(() => executionReportUrl(executionId.value, 'html'))
const jsonUrl = computed(() => executionReportUrl(executionId.value, 'json'))

onMounted(async () => {
  if (!executionId.value) return
  try {
    execution.value = await getExecution(executionId.value)
  } catch {
    // 404 时拦截器已提示
  }
})

async function loadJson() {
  if (format.value !== 'json' || jsonText.value) return
  loading.value = true
  jsonError.value = ''
  try {
    const resp = await fetch(jsonUrl.value)
    if (!resp.ok) {
      const body = await resp.json().catch(() => null)
      throw new Error(body?.error?.message || `HTTP ${resp.status}`)
    }
    jsonText.value = JSON.stringify(await resp.json(), null, 2)
  } catch (error) {
    jsonError.value = error instanceof Error ? error.message : String(error)
  } finally {
    loading.value = false
  }
}

async function switchFormat(value: 'html' | 'json') {
  format.value = value
  await loadJson()
}

async function copyJson() {
  try {
    await navigator.clipboard.writeText(jsonText.value)
    toastSuccess('已复制 JSON')
  } catch {
    toastError('复制失败（浏览器未授权剪贴板）')
  }
}
</script>

<template>
  <div style="display: flex; flex-direction: column; gap: 12px; height: calc(100vh - 96px)">
    <div class="toolbar">
      <h1>执行报告 #{{ executionId }}</h1>
      <span v-if="execution" class="tag"
            :class="execution.status === 'PASSED' ? 'tag-green'
              : execution.status === 'ERROR' ? 'tag-red' : 'tag-amber'">
        {{ execution.status }}
      </span>
      <span v-if="execution?.suite_name" class="tag tag-blue">{{ execution.suite_name }}</span>
      <span v-if="execution" class="muted">
        {{ execution.platform }} / {{ execution.engine_key }} ·
        通过 {{ execution.passed }} / 失败 {{ execution.failed }} / 异常 {{ execution.errored }} ·
        {{ execution.duration_ms ?? 0 }} ms
      </span>
      <div class="grow"></div>
      <div class="tabs">
        <button class="tab" :class="{ active: format === 'html' }" @click="switchFormat('html')">HTML</button>
        <button class="tab" :class="{ active: format === 'json' }" @click="switchFormat('json')">JSON</button>
      </div>
      <button class="btn btn-sm" @click="router.push('/executions')">返回执行列表</button>
      <a class="btn btn-sm" :href="`${htmlUrl}&download=1`">下载 HTML</a>
    </div>

    <section class="card" style="flex: 1; min-height: 0; display: flex; flex-direction: column">
      <div v-if="format === 'html'" style="flex: 1; min-height: 0">
        <iframe
          :src="htmlUrl"
          title="执行报告"
          style="width: 100%; height: 100%; border: 0; border-radius: 10px; background: #fff"
        ></iframe>
      </div>
      <div v-else class="card-body" style="flex: 1; min-height: 0; overflow: auto">
        <div class="toolbar" style="margin-bottom: 8px">
          <span class="muted">与 HTML 报告同源的数据结构，便于脚本消费</span>
          <div class="grow"></div>
          <button class="btn btn-sm" :disabled="!jsonText" @click="copyJson">复制</button>
        </div>
        <div v-if="loading" class="empty">加载中…</div>
        <div v-else-if="jsonError" class="empty" style="color: var(--red)">{{ jsonError }}</div>
        <pre v-else class="mono json-view">{{ jsonText }}</pre>
      </div>
    </section>
  </div>
</template>

<style>
.json-view {
  margin: 0; padding: 12px; background: #0f172a; color: #e2e8f0;
  border-radius: 8px; font-size: 12px; line-height: 1.55; overflow: auto;
}
</style>
