<script setup lang="ts">
/**
 * 用例编排（M3.2 / GAP-19）。
 *
 * 表单按动作字典的 params_schema 自动生成（Q-09）—— 不为 51 个动作各写一套表单，
 * 也不把用户丢进裸 JSON 编辑框。JSON 只在 array/object 类型参数上作为输入方式。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import {
  createCase, createStep, deleteCase, deleteStep, getCase, listActionDefs, listCases,
  listElements, listProjects, reorderSteps, runExecution, updateCase, updateStep,
} from '@/api'
import type { ActionDef, CaseDetail, ElementNode, TestStep } from '@/api/types'
import AppModal from '@/components/AppModal.vue'
import SchemaParams from '@/components/SchemaParams.vue'
import { toastError, toastInfo, toastSuccess } from '@/components/AppToast'

const router = useRouter()

const projects = ref<any[]>([])
const projectId = ref<number | null>(null)
const cases = ref<any[]>([])
const currentCase = ref<CaseDetail | null>(null)
const actions = ref<ActionDef[]>([])
const elements = ref<ElementNode[]>([])

const currentProject = computed(() => projects.value.find((p) => p.id === projectId.value) ?? null)

// ─────────────── 元素扁平化（树 → 可选列表）───────────────
interface FlatElement { id: number; label: string; depth: number; node_type: string }
const flatElements = computed<FlatElement[]>(() => {
  const out: FlatElement[] = []
  const walk = (nodes: ElementNode[], prefix: string[]) => {
    for (const node of nodes) {
      const path = [...prefix, node.element_name]
      out.push({
        id: node.id,
        label: path.join(' / '),
        depth: node.depth,
        node_type: node.node_type,
      })
      if (node.children?.length) walk(node.children, path)
    }
  }
  walk(elements.value, [])
  return out.filter((e) => e.node_type === 'ELEMENT')
})

const elementOptions = computed(() => {
  // 动作需要元素时，只让选元素（文件夹没有定位符，选了也执行不了）
  return flatElements.value
})

function elementLabel(id: number | null): string {
  if (!id) return '—'
  return flatElements.value.find((e) => e.id === id)?.label ?? `#${id}`
}

// ─────────────── 动作选择 ───────────────
const actionByKey = computed<Record<string, ActionDef>>(() =>
  Object.fromEntries(actions.value.map((a) => [a.action_key, a])))

const actionOptions = computed(() => {
  const platform = currentProject.value?.platform
  return actions.value.filter((a) => !platform || a.platforms.includes(platform))
})

const actionName = (key: string) => actionByKey.value[key]?.name ?? key

// ─────────────── 加载 ───────────────
onMounted(async () => {
  const [projResp, actionResp] = await Promise.all([listProjects(), listActionDefs()])
  projects.value = projResp.items
  actions.value = actionResp.items
  if (projects.value.length) {
    projectId.value = projects.value[0].id
    await loadProject()
  }
})

watch(projectId, () => { void loadProject() })

async function loadProject() {
  if (!projectId.value) return
  const [caseResp, elementResp] = await Promise.all([
    listCases(projectId.value),
    listElements(projectId.value),
  ])
  cases.value = caseResp.items
  elements.value = elementResp.items
  if (currentCase.value && !cases.value.some((c) => c.id === currentCase.value!.id)) {
    currentCase.value = null
  }
  if (currentCase.value) {
    await openCase(currentCase.value.id)
  } else if (cases.value.length) {
    // 进入页面先给一个可操作的上下文，而不是一块空面板
    await openCase(cases.value[0].id)
  }
}

async function openCase(id: number) {
  currentCase.value = await getCase(id)
}

// ─────────────── 用例 ───────────────
const showCaseForm = ref(false)
const caseForm = ref({ title: '', description: '' })
const editingCaseId = ref<number | null>(null)

function openCreateCase() {
  editingCaseId.value = null
  caseForm.value = { title: '', description: '' }
  showCaseForm.value = true
}

function openEditCase() {
  if (!currentCase.value) return
  editingCaseId.value = currentCase.value.id
  caseForm.value = {
    title: currentCase.value.title,
    description: currentCase.value.description ?? '',
  }
  showCaseForm.value = true
}

async function saveCase() {
  const title = caseForm.value.title.trim()
  if (!title) {
    toastError('用例标题不能为空')
    return
  }
  if (editingCaseId.value) {
    await updateCase(editingCaseId.value, {
      title, description: caseForm.value.description || undefined,
    })
    toastSuccess('已保存')
  } else if (projectId.value) {
    const created = await createCase(projectId.value, {
      title, description: caseForm.value.description || undefined,
    })
    toastSuccess('已创建用例')
    await loadProject()
    await openCase(created.id)
  }
  showCaseForm.value = false
  await loadProject()
}

async function removeCase(item: any) {
  if (!window.confirm(`删除用例「${item.title}」？步骤会保留但不再执行。`)) return
  await deleteCase(item.id)
  if (currentCase.value?.id === item.id) currentCase.value = null
  toastSuccess('已删除')
  await loadProject()
}

async function runCase() {
  if (!currentCase.value || !projectId.value) return
  const result = await runExecution({
    project_id: projectId.value, case_ids: [currentCase.value.id],
  })
  toastInfo(`已提交执行 #${result.id}`)
  await router.push('/executions')
}

// ─────────────── 步骤表单 ───────────────
const showStepForm = ref(false)
const editingStepId = ref<number | null>(null)
const stepForm = ref<{
  action_key: string
  element_id: number | null
  params: Record<string, any>
  output_var: string
  timeout_ms: number | null
  on_failure: 'ABORT' | 'CONTINUE' | 'RETRY'
  retry_times: number
  enabled: boolean
  remark: string
  seq: number | null
}>(blankStep())

function blankStep() {
  return {
    action_key: '',
    element_id: null as number | null,
    params: {} as Record<string, any>,
    output_var: '',
    timeout_ms: null as number | null,
    on_failure: 'ABORT' as 'ABORT' | 'CONTINUE' | 'RETRY',
    retry_times: 0,
    enabled: true,
    remark: '',
    seq: null as number | null,
  }
}

const selectedAction = computed<ActionDef | null>(() =>
  stepForm.value.action_key ? actionByKey.value[stepForm.value.action_key] ?? null : null)

const needsElement = computed(() => {
  const action = selectedAction.value
  if (!action) return false
  return action.requires_element
    || (action.action_key === 'screenshot' && stepForm.value.params.target === 'element')
})

// M3.8（GAP-12）：switch_to_iframe 绑定元素是"可选语义"（绑了按元素进入，
// 不绑走 index/弹栈）——选择器要显示，但不参与必填校验。
const showsElement = computed(() =>
  needsElement.value || selectedAction.value?.action_key === 'switch_to_iframe')

watch(() => stepForm.value.action_key, () => {
  // 换动作时清空参数，避免把上一个动作的字段带到下一个
  stepForm.value.params = {}
  stepForm.value.element_id = null
})

function openCreateStep() {
  if (!currentCase.value) return
  editingStepId.value = null
  stepForm.value = blankStep()
  stepForm.value.seq = (currentCase.value.steps?.length ?? 0) + 1
  showStepForm.value = true
}

function openEditStep(step: TestStep) {
  editingStepId.value = step.id
  stepForm.value = {
    action_key: step.action_key,
    element_id: step.element_id,
    params: JSON.parse(JSON.stringify(step.params ?? {})),
    output_var: step.output_var ?? '',
    timeout_ms: step.timeout_ms,
    on_failure: step.on_failure,
    retry_times: step.retry_times,
    enabled: step.enabled,
    remark: step.remark ?? '',
    seq: step.seq,
  }
  showStepForm.value = true
}

const paramsRef = ref<InstanceType<typeof SchemaParams> | null>(null)

async function saveStep() {
  if (!currentCase.value) return
  if (!stepForm.value.action_key) {
    toastError('请选择动作')
    return
  }
  if (needsElement.value && !stepForm.value.element_id) {
    toastError('该动作需要绑定元素')
    return
  }
  if (paramsRef.value?.hasErrors()) {
    toastError('有参数 JSON 格式不合法')
    return
  }

  const body: any = {
    action_key: stepForm.value.action_key,
    // M3.8：可选绑定动作（switch_to_iframe）用户选了元素就保留；其余动作
    // 选择器不显示、值恒为 null —— 与后端三态绑定规则对齐。
    element_id: stepForm.value.element_id ?? null,
    params: stepForm.value.params,
    output_var: stepForm.value.output_var || null,
    timeout_ms: stepForm.value.timeout_ms ?? null,
    on_failure: stepForm.value.on_failure,
    retry_times: stepForm.value.retry_times,
    enabled: stepForm.value.enabled,
    remark: stepForm.value.remark || null,
  }
  try {
    if (editingStepId.value) {
      await updateStep(currentCase.value.id, editingStepId.value, body)
      toastSuccess('步骤已更新')
    } else {
      body.seq = stepForm.value.seq
      await createStep(currentCase.value.id, body)
      toastSuccess('步骤已添加')
    }
    showStepForm.value = false
    await openCase(currentCase.value.id)
    await loadProject()
  } catch {
    // 后端已返回具体原因（schema 不符 / seq 冲突 / 元素不属于项目）
  }
}

async function removeStep(step: TestStep) {
  if (!currentCase.value) return
  if (!window.confirm(`删除第 ${step.seq} 步（${actionName(step.action_key)}）？`)) return
  await deleteStep(currentCase.value.id, step.id)
  toastSuccess('已删除')
  await openCase(currentCase.value.id)
  await loadProject()
}

async function move(step: TestStep, delta: number) {
  if (!currentCase.value) return
  const steps = [...(currentCase.value.steps ?? [])].sort((a, b) => a.seq - b.seq)
  const index = steps.findIndex((s) => s.id === step.id)
  const target = index + delta
  if (target < 0 || target >= steps.length) return
  const ids = steps.map((s) => s.id)
  ;[ids[index], ids[target]] = [ids[target], ids[index]]
  await reorderSteps(currentCase.value.id, ids)
  await openCase(currentCase.value.id)
}

function paramSummary(step: TestStep): string {
  const entries = Object.entries(step.params ?? {})
    .filter(([k]) => k !== 'output_var')
  if (!entries.length) return step.output_var ? `→ ${step.output_var}` : ''
  const text = entries
    .map(([k, v]) => `${k}=${typeof v === 'object' ? JSON.stringify(v) : String(v)}`)
    .join(' · ')
  return step.output_var ? `${text} → ${step.output_var}` : text
}
</script>

<template>
  <div style="display: flex; flex-direction: column; gap: 12px">
    <div class="toolbar">
      <h1>用例编排</h1>
      <select v-model.number="projectId" class="select" style="width: 220px">
        <option v-for="project in projects" :key="project.id" :value="project.id">{{ project.name }}</option>
      </select>
      <span v-if="currentProject" class="tag">
        {{ currentProject.platform }} / {{ currentProject.engine_key }}
      </span>
      <span class="muted">项目 → 用例集 → 用例 → 元素 + 动作</span>
      <div class="grow"></div>
      <button class="btn btn-primary" @click="openCreateCase">新建用例</button>
    </div>

    <div class="library" style="grid-template-columns: 300px minmax(0, 1fr)">
      <!-- 用例列表 -->
      <section class="card">
        <div class="card-header">
          <h2>用例</h2>
          <span class="muted">{{ cases.length }} 条</span>
        </div>
        <div style="max-height: 620px; overflow: auto">
          <div
            v-for="item in cases"
            :key="item.id"
            class="case-item"
            :class="{ active: currentCase?.id === item.id }"
            @click="openCase(item.id)"
          >
            <div>
              <b>#{{ item.id }}</b> {{ item.title }}
              <div v-if="item.description" class="muted" style="font-size: 12px">
                {{ item.description }}
              </div>
            </div>
            <button class="btn btn-sm btn-ghost btn-danger" title="删除用例" @click.stop="removeCase(item)">✕</button>
          </div>
          <div v-if="!cases.length" class="empty">还没有用例</div>
        </div>
      </section>

      <!-- 步骤编辑器 -->
      <section class="card" v-if="currentCase">
        <div class="card-header">
          <div>
            <h2>#{{ currentCase.id }} {{ currentCase.title }}</h2>
            <span class="muted" style="font-size: 12px">
              {{ currentCase.steps?.length ?? 0 }} 个步骤 · seq 决定执行顺序
            </span>
          </div>
          <div class="toolbar">
            <button class="btn btn-sm" @click="openEditCase">改标题</button>
            <button class="btn btn-sm" @click="runCase">运行该用例</button>
            <button class="btn btn-sm btn-primary" @click="openCreateStep">添加步骤</button>
          </div>
        </div>

        <table>
          <thead>
            <tr>
              <th style="width: 52px">seq</th>
              <th style="width: 150px">动作</th>
              <th style="width: 170px">元素</th>
              <th>参数</th>
              <th style="width: 118px">失败策略</th>
              <th style="width: 150px"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(step, index) in (currentCase.steps ?? []).slice().sort((a, b) => a.seq - b.seq)"
                :key="step.id" :class="{ 'row-disabled': !step.enabled }">
              <td class="mono">{{ step.seq }}</td>
              <td>
                <span class="mono">{{ step.action_key }}</span>
                <div class="muted" style="font-size: 12px">{{ actionName(step.action_key) }}</div>
              </td>
              <td class="muted" style="font-size: 12px">{{ elementLabel(step.element_id) }}</td>
              <td class="mono" style="font-size: 12px; max-width: 360px; overflow: hidden; text-overflow: ellipsis">
                {{ paramSummary(step) }}
              </td>
              <td>
                <span class="tag" :class="step.on_failure === 'CONTINUE' ? '' : 'tag-amber'">
                  {{ step.on_failure }}{{ step.retry_times ? ` ×${step.retry_times}` : '' }}
                </span>
              </td>
              <td>
                <div class="toolbar" style="justify-content: flex-end">
                  <button class="btn btn-sm btn-ghost" :disabled="index === 0" title="上移" @click="move(step, -1)">↑</button>
                  <button class="btn btn-sm btn-ghost" :disabled="index === (currentCase.steps?.length ?? 0) - 1"
                          title="下移" @click="move(step, 1)">↓</button>
                  <button class="btn btn-sm" @click="openEditStep(step)">编辑</button>
                  <button class="btn btn-sm btn-ghost btn-danger" @click="removeStep(step)">✕</button>
                </div>
              </td>
            </tr>
            <tr v-if="!currentCase.steps?.length">
              <td colspan="6" class="empty">还没有步骤，点右上角「添加步骤」</td>
            </tr>
          </tbody>
        </table>
      </section>
      <section v-else class="card">
        <div class="card-body empty">从左侧选择一个用例开始编排</div>
      </section>
    </div>

    <!-- 用例表单 -->
    <AppModal
      v-if="showCaseForm"
      :title="editingCaseId ? '编辑用例' : '新建用例'"
      @close="showCaseForm = false"
      @confirm="saveCase"
    >
      <div class="field">
        <label>标题</label>
        <input v-model="caseForm.title" class="input" placeholder="如：登录成功跳转首页" />
      </div>
      <div class="field">
        <label>描述</label>
        <input v-model="caseForm.description" class="input" placeholder="可选" />
      </div>
    </AppModal>

    <!-- 步骤表单 -->
    <AppModal
      v-if="showStepForm"
      :title="editingStepId ? `编辑步骤 #${editingStepId}` : '添加步骤'"
      width="720px"
      @close="showStepForm = false"
      @confirm="saveStep"
    >
      <div class="field">
        <label>动作</label>
        <select v-model="stepForm.action_key" class="select">
          <option value="">选择动作…</option>
          <option v-for="action in actionOptions" :key="action.action_key" :value="action.action_key">
            {{ action.name }}（{{ action.action_key }}）
          </option>
        </select>
        <div v-if="selectedAction" class="muted" style="font-size: 12px">
          {{ selectedAction.category }} · 支持：{{ selectedAction.engines.join(' / ') }}
        </div>
      </div>

      <div class="field" v-if="showsElement">
        <label>绑定元素 <span v-if="needsElement" style="color: var(--red)">*</span></label>
        <select v-model.number="stepForm.element_id" class="select">
          <option :value="null">选择元素…</option>
          <option v-for="option in elementOptions" :key="option.id" :value="option.id">
            {{ option.label }}
          </option>
        </select>
        <div v-if="selectedAction?.action_key === 'screenshot'" class="muted" style="font-size: 12px">
          screenshot 只有在 target=element 时才需要元素
        </div>
        <div v-if="selectedAction?.action_key === 'switch_to_iframe'" class="muted" style="font-size: 12px">
          绑定 iframe 元素即按元素进入；不绑定可用 index（两者二选一）
        </div>
      </div>

      <!-- 按 params_schema 自动生成 -->
      <SchemaParams
        ref="paramsRef"
        v-model="stepForm.params"
        :schema="selectedAction?.params_schema ?? null"
        :exclude="['output_var']"
      />

      <div class="field">
        <label>输出变量（后续步骤用 <span class="mono">${name}</span> 引用）</label>
        <input v-model="stepForm.output_var" class="input mono" placeholder="可选，如 welcome_text" />
      </div>

      <div style="display: grid; grid-template-columns: 1fr 1fr 90px; gap: 10px">
        <div class="field">
          <label>失败策略</label>
          <select v-model="stepForm.on_failure" class="select">
            <option value="ABORT">ABORT（中止用例）</option>
            <option value="CONTINUE">CONTINUE（继续下一步）</option>
            <option value="RETRY">RETRY（重试后中止）</option>
          </select>
        </div>
        <div class="field">
          <label>重试次数（0–5）</label>
          <input v-model.number="stepForm.retry_times" class="input" type="number" min="0" max="5" />
        </div>
        <div class="field">
          <label>超时 ms</label>
          <input v-model.number="stepForm.timeout_ms" class="input" type="number" placeholder="默认" />
        </div>
      </div>

      <div class="field">
        <label style="font-weight: 400">
          <input v-model="stepForm.enabled" type="checkbox" /> 启用该步骤
        </label>
      </div>
      <div class="field">
        <label>备注</label>
        <input v-model="stepForm.remark" class="input" placeholder="可选" />
      </div>
    </AppModal>
  </div>
</template>

<style>
.case-item {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  padding: 9px 12px; border-bottom: 1px solid var(--border); cursor: pointer; font-size: 13px;
}
.case-item:hover { background: #f6f8fb; }
.case-item.active { background: #eef4ff; box-shadow: inset 3px 0 0 #2563eb; }
.row-disabled { opacity: 0.5; }
</style>
