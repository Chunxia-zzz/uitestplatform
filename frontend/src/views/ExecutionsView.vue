<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import {
  cancelExecution, getExecution, listArtifacts, listCases, listExecutions, listProjects,
  listSuites, runExecution,
} from '@/api'
import type { Artifact, Execution, Suite } from '@/api/types'
import { toastInfo } from '@/components/AppToast'

const router = useRouter()

const projects = ref<any[]>([])
const projectId = ref<number | null>(null)
const suites = ref<Suite[]>([])
const suiteId = ref<number | null>(null)
const cases = ref<any[]>([])
const executions = ref<Execution[]>([])
const detail = ref<Execution | null>(null)
const artifactsByStep = ref<Record<number, Artifact[]>>({})
const running = ref(false)
const progress = ref<{ done_steps: number; total_steps: number | null } | null>(null)
let timer: number | undefined

const currentProject = computed(() => projects.value.find((p) => p.id === projectId.value) ?? null)
const TERMINAL = ['PASSED', 'FAILED', 'ERROR', 'CANCELLED']
const progressPct = computed(() => {
  const p = progress.value
  if (!p || !p.total_steps) return 0
  return Math.min(100, Math.round((p.done_steps / p.total_steps) * 100))
})

onMounted(async () => {
  const resp = await listProjects()
  projects.value = resp.items
  if (projects.value.length) {
    projectId.value = projects.value[0].id
    await loadProject()
  }
})

onBeforeUnmount(() => window.clearTimeout(timer))

async function loadProject() {
  if (!projectId.value) return
  const [caseResp, suiteResp] = await Promise.all([
    listCases(projectId.value),
    listSuites(projectId.value),
  ])
  cases.value = caseResp.items
  suites.value = suiteResp.items
  if (suiteId.value && !suites.value.some((s) => s.id === suiteId.value)) suiteId.value = null
  await loadExecutions()
}

async function loadExecutions() {
  if (!projectId.value) return
  const resp = await listExecutions(projectId.value, suiteId.value)
  executions.value = resp.items
}

async function onFilterChange() {
  await loadExecutions()
  if (detail.value && !executions.value.some((e) => e.id === detail.value!.id)) {
    detail.value = null
    artifactsByStep.value = {}
  }
}

async function run() {
  if (!projectId.value || !cases.value.length) return
  // M3.1：202 立即返回，随后轮询 —— 不再阻塞等整批跑完
  const created = await runExecution({
    project_id: projectId.value,
    case_ids: [cases.value[0].id],
  })
  toastInfo(`已提交执行 #${created.id}（${created.status}）`)
  running.value = true
  progress.value = { done_steps: 0, total_steps: null }
  pump(created.id)
}

async function pump(id: number) {
  window.clearTimeout(timer)
  const data = await getExecution(id)
  detail.value = data
  progress.value = (data as any).progress ?? null
  if (TERMINAL.includes(data.status)) {
    running.value = false
    await Promise.all([loadExecutions(), loadArtifacts(id)])
    toastInfo(`执行 #${id} 结束：${data.status}`)
    return
  }
  timer = window.setTimeout(() => pump(id), 5000)   // D25：5s 一次（≤30s 约束内），不限次数
}

/** 产物按 step_result_id 分组 —— 表格里按行显示截图入口（GAP-34） */
async function loadArtifacts(id: number) {
  try {
    const resp = await listArtifacts(id)
    const grouped: Record<number, Artifact[]> = {}
    for (const item of resp.items) {
      if (!item.step_result_id) continue
      ;(grouped[item.step_result_id] ||= []).push(item)
    }
    artifactsByStep.value = grouped
  } catch {
    artifactsByStep.value = {}
  }
}

async function stop() {
  const id = detail.value?.id
  if (!id) return
  await cancelExecution(id)
  toastInfo('已请求取消（在步骤之间生效）')
  pump(id)
}

async function open(execution: Execution) {
  detail.value = await getExecution(execution.id)
  progress.value = (detail.value as any).progress ?? null
  artifactsByStep.value = {}
  if (TERMINAL.includes(detail.value.status)) {
    await loadArtifacts(execution.id)
  }
  if (!TERMINAL.includes(detail.value.status)) {
    running.value = true
    pump(execution.id)
  }
}

function openReport(id: number) {
  void router.push(`/executions/${id}/report`)
}

function rowClass(index: number | null) {
  return index && index > 0 ? 'warn-row' : ''
}
</script>

<template>
  <div style="display: flex; flex-direction: column; gap: 12px">
    <div class="toolbar">
      <h1>执行结果</h1>
      <select v-model.number="projectId" class="select" style="width: 220px" @change="loadProject">
        <option v-for="project in projects" :key="project.id" :value="project.id">{{ project.name }}</option>
      </select>
      <select v-model.number="suiteId" class="select" style="width: 180px" @change="onFilterChange">
        <option :value="null">全部用例集</option>
        <option v-for="suite in suites" :key="suite.id" :value="suite.id">{{ suite.name }}</option>
      </select>
      <span v-if="currentProject" class="tag">
        {{ currentProject.platform }} / {{ currentProject.engine_key }}
      </span>
      <div class="grow"></div>
      <button v-if="running" class="btn btn-danger" @click="stop">取消执行</button>
      <button class="btn btn-primary" :disabled="running || !cases.length" @click="run">
        {{ running ? '执行中…' : '运行首个用例' }}
      </button>
    </div>

    <div v-if="running && progress" class="card">
      <div class="card-body">
        <div class="toolbar" style="font-size: 13px">
          <span>执行中</span>
          <div class="grow"></div>
          <span class="muted">
            {{ progress.done_steps }}<template v-if="progress.total_steps">/{{ progress.total_steps }}</template>
            步
          </span>
        </div>
        <div style="height: 6px; background: #eef0f3; border-radius: 999px; margin-top: 8px">
          <div :style="{ width: (progressPct || 8) + '%', height: '100%', background: '#2563eb', borderRadius: '999px', transition: 'width .3s' }"></div>
        </div>
      </div>
    </div>

    <section class="card">
      <div class="card-header">
        <h2>执行批次</h2>
        <span class="muted">{{ executions.length }} 条</span>
      </div>
      <table>
        <thead>
          <tr><th>#</th><th>用例集</th><th>状态</th><th>通过 / 失败 / 异常 / 跳过</th><th>耗时</th><th>开始时间</th><th></th></tr>
        </thead>
        <tbody>
          <tr v-for="execution in executions" :key="execution.id">
            <td class="mono">{{ execution.id }}</td>
            <td class="muted">{{ execution.suite_name || '—' }}</td>
            <td>
              <span class="tag" :class="execution.status === 'PASSED' ? 'tag-green'
                : execution.status === 'ERROR' ? 'tag-red' : 'tag-amber'">{{ execution.status }}</span>
            </td>
            <td>
              {{ execution.passed }} / {{ execution.failed }} /
              {{ execution.errored }} / {{ execution.skipped }}
            </td>
            <td class="muted">{{ execution.duration_ms }} ms</td>
            <td class="muted">{{ execution.started_at }}</td>
            <td><button class="btn btn-sm" @click="open(execution)">详情</button></td>
          </tr>
          <tr v-if="!executions.length"><td colspan="7" class="empty">还没有执行记录</td></tr>
        </tbody>
      </table>
    </section>

    <section v-if="detail" class="card">
      <div class="card-header">
        <h2>批次 #{{ detail.id }} 步骤明细</h2>
        <div class="toolbar">
          <span class="muted">fallback_index &gt; 0 为回退命中（黄底）</span>
          <button
            v-if="TERMINAL.includes(detail.status)"
            class="btn btn-sm"
            @click="openReport(detail.id)"
          >查看报告</button>
        </div>
      </div>
      <div v-for="group in detail.cases" :key="group.case_id" style="padding: 8px 0">
        <div style="padding: 6px 16px" class="muted">用例 #{{ group.case_id }} «{{ group.title }}»</div>
        <table>
          <thead>
            <tr>
              <th>seq</th><th>动作</th><th>元素</th><th>状态</th><th>尝试</th><th>耗时</th>
              <th>used_locator_id</th><th>fallback_index</th><th>产物</th><th>消息</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(step, idx) in group.steps" :key="`${step.seq}-${step.attempt}-${idx}`" :class="rowClass(step.fallback_index)">
              <td>{{ step.seq }}</td>
              <td class="mono">{{ step.action_key }}</td>
              <td class="muted">{{ step.element_id ?? '—' }}</td>
              <td>
                <span class="tag" :class="step.status === 'PASSED' ? 'tag-green'
                  : step.status === 'FAILED' ? 'tag-amber' : step.status === 'ERROR' ? 'tag-red' : ''">
                  {{ step.status }}
                </span>
              </td>
              <td class="mono" :class="(step.attempt ?? 1) > 1 ? 'tag tag-blue' : ''">{{ step.attempt ?? 1 }}</td>
              <td class="muted">{{ step.duration_ms }} ms</td>
              <td class="mono">{{ step.used_locator_id ?? '—' }}</td>
              <td class="mono">
                <span :class="step.fallback_index ? 'tag tag-amber' : ''">{{ step.fallback_index ?? '—' }}</span>
              </td>
              <td>
                <a
                  v-for="artifact in (artifactsByStep[step.id] || [])"
                  :key="artifact.id"
                  class="tag tag-blue"
                  :href="artifact.url"
                  target="_blank"
                  rel="noreferrer"
                  style="text-decoration: none; margin-right: 4px"
                >截图{{ artifact.id }}</a>
                <span v-if="!(artifactsByStep[step.id] || []).length" class="muted">—</span>
              </td>
              <td class="muted" style="max-width: 320px; overflow: hidden; text-overflow: ellipsis">
                {{ step.message || '' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="!detail.cases?.length" class="empty">该批次还没有步骤结果</div>
    </section>
  </div>
</template>

<style>
.warn-row { background: #fdf6e7; }
</style>
