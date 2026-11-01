<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  addSuiteCases, createSuite, deleteSuite, getSuite, listCases, listProjects, listSuites,
  removeSuiteCase, runSuite, toggleSuiteCase, updateSuite,
} from '@/api'
import type { Suite } from '@/api/types'
import AppModal from '@/components/AppModal.vue'
import { toastInfo, toastSuccess } from '@/components/AppToast'

const projects = ref<any[]>([])
const projectId = ref<number | null>(null)
const suites = ref<Suite[]>([])
const projectCases = ref<any[]>([])
const detail = ref<Suite | null>(null)

const showForm = ref(false)
const editing = ref<Suite | null>(null)
const form = ref<{ name: string; description: string; schedule_cron: string; schedule_enabled: boolean }>({
  name: '', description: '', schedule_cron: '', schedule_enabled: false,
})
const addCaseId = ref<number | null>(null)

const currentProject = computed(() => projects.value.find((p) => p.id === projectId.value) ?? null)
const candidateCases = computed(() => {
  const used = new Set((detail.value?.cases ?? []).map((c) => c.case_id))
  return projectCases.value.filter((c) => !used.has(c.id))
})

onMounted(async () => {
  const resp = await listProjects()
  projects.value = resp.items
  if (projects.value.length) {
    projectId.value = projects.value[0].id
    await load()
  }
})

async function load() {
  if (!projectId.value) return
  const [suiteResp, caseResp] = await Promise.all([
    listSuites(projectId.value),
    listCases(projectId.value),
  ])
  suites.value = suiteResp.items
  projectCases.value = caseResp.items
  if (detail.value) {
    await openSuite(detail.value.id)
  }
}

async function openSuite(id: number) {
  detail.value = await getSuite(id)
}

function openCreate() {
  editing.value = null
  form.value = { name: '', description: '', schedule_cron: '', schedule_enabled: false }
  showForm.value = true
}

function openEdit(suite: Suite) {
  editing.value = suite
  form.value = {
    name: suite.name,
    description: suite.description ?? '',
    schedule_cron: suite.schedule_cron ?? '',
    schedule_enabled: suite.schedule_enabled,
  }
  showForm.value = true
}

async function save() {
  if (!projectId.value || !form.value.name.trim()) return
  const body = {
    name: form.value.name.trim(),
    description: form.value.description || undefined,
    schedule_cron: form.value.schedule_cron.trim() || null,
    schedule_enabled: form.value.schedule_enabled,
  }
  if (editing.value) {
    await updateSuite(editing.value.id, body)
    toastSuccess('已保存')
  } else {
    await createSuite(projectId.value, body)
    toastSuccess('已创建用例集')
  }
  showForm.value = false
  await load()
}

async function remove(suite: Suite) {
  if (!window.confirm(`删除用例集「${suite.name}」？（不会删除用例本身）`)) return
  await deleteSuite(suite.id)
  if (detail.value?.id === suite.id) detail.value = null
  await load()
}

async function run(suite: Suite) {
  const result = await runSuite(suite.id)
  toastInfo(`已提交执行 #${result.id}（${result.suite_name} · ${result.case_count} 条用例）`)
  await load()
}

async function addCase() {
  if (!detail.value || !addCaseId.value) return
  const result = await addSuiteCases(detail.value.id, [addCaseId.value])
  if (result.invalid.length) toastInfo('该用例不属于当前项目')
  addCaseId.value = null
  await openSuite(detail.value.id)
  await load()
}

async function removeCase(caseId: number) {
  if (!detail.value) return
  await removeSuiteCase(detail.value.id, caseId)
  await openSuite(detail.value.id)
  await load()
}

/** GAP-38：临时跳一条用例，保留成员与排序（移除再添加会丢 sort） */
async function toggleCase(item: any) {
  if (!detail.value) return
  await toggleSuiteCase(detail.value.id, item.case_id, !item.enabled)
  await openSuite(detail.value.id)
}
</script>

<template>
  <div style="display: flex; flex-direction: column; gap: 12px">
    <div class="toolbar">
      <h1>用例集</h1>
      <select v-model.number="projectId" class="select" style="width: 220px" @change="load">
        <option v-for="project in projects" :key="project.id" :value="project.id">{{ project.name }}</option>
      </select>
      <span v-if="currentProject" class="tag">
        {{ currentProject.platform }} / {{ currentProject.engine_key }}
      </span>
      <span class="muted">项目 → 用例集 → 用例 → 元素+动作；用例集是执行单元</span>
      <div class="grow"></div>
      <button class="btn btn-primary" @click="openCreate">新建用例集</button>
    </div>

    <div class="library" style="grid-template-columns: minmax(0, 1fr) 380px">
      <section class="card">
        <div class="card-header"><h2>用例集列表</h2><span class="muted">{{ suites.length }} 个</span></div>
        <table>
          <thead>
            <tr><th>名称</th><th>用例数</th><th>定时</th><th>上次运行</th><th></th></tr>
          </thead>
          <tbody>
            <tr v-for="suite in suites" :key="suite.id">
              <td>
                <a href="#" @click.prevent="openSuite(suite.id)">{{ suite.name }}</a>
                <div v-if="suite.description" class="muted" style="font-size: 12px">{{ suite.description }}</div>
              </td>
              <td>{{ suite.case_count ?? 0 }}</td>
              <td>
                <span v-if="suite.schedule_enabled && suite.schedule_cron" class="tag tag-blue mono">
                  {{ suite.schedule_cron }}
                </span>
                <span v-else class="muted">手动</span>
              </td>
              <td class="muted">{{ suite.last_run_at || '—' }}</td>
              <td class="toolbar" style="justify-content: flex-end">
                <button class="btn btn-sm btn-primary" :disabled="!suite.case_count" @click="run(suite)">运行</button>
                <button class="btn btn-sm" @click="openEdit(suite)">编辑</button>
                <button class="btn btn-sm btn-danger" @click="remove(suite)">删除</button>
              </td>
            </tr>
            <tr v-if="!suites.length"><td colspan="5" class="empty">还没有用例集</td></tr>
          </tbody>
        </table>
      </section>

      <section class="card" v-if="detail">
        <div class="card-header">
          <h2>{{ detail.name }}</h2>
          <button class="btn btn-sm" @click="openEdit(detail)">编辑</button>
        </div>
        <div class="card-body">
          <div class="muted" style="font-size: 12px; margin-bottom: 8px">
            定时：{{ detail.schedule_enabled && detail.schedule_cron ? detail.schedule_cron : '仅手动' }} ·
            上次运行：{{ detail.last_run_at || '—' }} ·
            勾选框控制单次执行是否包含该用例
          </div>
          <div v-for="item in detail.cases" :key="item.case_id" class="locator-row"
               style="grid-template-columns: 24px 1fr 60px"
               :class="{ 'member-off': !item.enabled }">
            <input
              type="checkbox"
              :checked="item.enabled"
              :title="item.enabled ? '点击跳过该用例' : '点击启用该用例'"
              @change="toggleCase(item)"
            />
            <span>#{{ item.case_id }} {{ item.title }}</span>
            <button class="btn btn-sm btn-ghost btn-danger" @click="removeCase(item.case_id)">移除</button>
          </div>
          <div v-if="!detail.cases?.length" class="empty">用例集为空</div>

          <div style="display: flex; gap: 8px; margin-top: 12px">
            <select v-model.number="addCaseId" class="select">
              <option :value="null">选择要加入的用例…</option>
              <option v-for="c in candidateCases" :key="c.id" :value="c.id">#{{ c.id }} {{ c.title }}</option>
            </select>
            <button class="btn" :disabled="!addCaseId" @click="addCase">加入</button>
          </div>
          <div style="margin-top: 12px">
            <button class="btn btn-primary" @click="run(detail)">运行该用例集</button>
          </div>
        </div>
      </section>
      <section class="card" v-else>
        <div class="card-body empty">从左侧选择一个用例集查看成员</div>
      </section>
    </div>

    <AppModal
      v-if="showForm"
      :title="editing ? '编辑用例集' : '新建用例集'"
      @close="showForm = false"
      @confirm="save"
    >
      <div class="field">
        <label>名称</label>
        <input v-model="form.name" class="input" placeholder="如：冒烟回归" />
      </div>
      <div class="field">
        <label>描述</label>
        <input v-model="form.description" class="input" placeholder="可选" />
      </div>
      <div class="field">
        <label>定时 cron（5 段：分 时 日 月 周，留空=只手动）</label>
        <input v-model="form.schedule_cron" class="input mono" placeholder="0 9 * * 1-5" />
      </div>
      <div class="field">
        <label>
          <input v-model="form.schedule_enabled" type="checkbox" :disabled="!form.schedule_cron.trim()" />
          启用定时（按服务器时区）
        </label>
      </div>
    </AppModal>
  </div>
</template>
