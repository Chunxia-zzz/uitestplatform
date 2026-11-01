<script setup lang="ts">
/**
 * 快速接入（M3.4）：填网页地址 + 一组动作 → 自动建项目/元素/用例/用例集并执行。
 *
 * 前端做两处"便捷 → 规范"的转换（后端只认规范形态，见 D2-M3.4 §1.5）：
 * 1. 动作行里内联的元素名与定位符 → 聚合去重成 `elements[]`；
 * 2. 动作参数用 SchemaParams 按 `params_schema` 生成，与 StepEditor 同一份组件。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { listActionDefs, scaffold } from '@/api'
import type { ActionDef } from '@/api/types'
import SchemaParams from '@/components/SchemaParams.vue'
import { toastError, toastInfo, toastSuccess } from '@/components/AppToast'

const router = useRouter()

interface LocatorRow { locator_type: string; locator_value: string }
interface ActionRow {
  uid: number
  action_key: string
  element_name: string
  locators: LocatorRow[]
  params: Record<string, any>
  output_var: string
}

let uidSeed = 0
const nextUid = () => ++uidSeed

const actions = ref<ActionDef[]>([])
const submitting = ref(false)
const result = ref<any>(null)
const errorText = ref('')

// ── 基础输入 ─────────────────────────────────────────────
const url = ref('http://127.0.0.1:8899/login.html')
const projectCode = ref('demo-web-scaffold')
const projectName = ref('Demo Web 中台')
const caseTitle = ref('登录主链路')
const suiteName = ref('冒烟回归')

// 本期只支持 WEB（M4 前 Appium/u2 是桩）
const platform = 'WEB'
const engineKey = 'playwright'

const rows = ref<ActionRow[]>([])

const actionByKey = computed<Record<string, ActionDef>>(() =>
  Object.fromEntries(actions.value.map((a) => [a.action_key, a])))

const actionOptions = computed(() =>
  actions.value.filter((a) => a.platforms.includes(platform)))

onMounted(async () => {
  const resp = await listActionDefs()
  actions.value = resp.items
})

// ── 动作行 ───────────────────────────────────────────────
function blankRow(actionKey = '', elementName = '', params: Record<string, any> = {},
                   locators: LocatorRow[] = []): ActionRow {
  return {
    uid: nextUid(), action_key: actionKey, element_name: elementName,
    locators, params, output_var: '',
  }
}

function addRow() {
  rows.value.push(blankRow())
}

function removeRow(index: number) {
  rows.value.splice(index, 1)
}

function addLocator(row: ActionRow) {
  row.locators.push({ locator_type: 'css', locator_value: '' })
}

function removeLocator(row: ActionRow, index: number) {
  row.locators.splice(index, 1)
}

function needsElement(row: ActionRow): boolean {
  const action = actionByKey.value[row.action_key]
  if (!action) return false
  return action.requires_element
    || (action.action_key === 'screenshot' && row.params.target === 'element')
}

function schemaOf(row: ActionRow) {
  return actionByKey.value[row.action_key]?.params_schema ?? null
}

function onActionChange(row: ActionRow) {
  // 换动作时清空参数与元素，避免把上一个动作的字段带过去
  row.params = {}
  row.element_name = ''
  row.locators = []
}

// ── 示例 ─────────────────────────────────────────────────
function loadExample() {
  url.value = 'http://127.0.0.1:8899/login.html'
  projectCode.value = 'demo-web-scaffold'
  projectName.value = 'Demo Web 中台'
  caseTitle.value = '登录主链路'
  suiteName.value = '冒烟回归'
  rows.value = [
    blankRow('navigate', '', { url: '/login.html' }),
    blankRow('input', '用户名输入框', { text: 'jerry' },
             [{ locator_type: 'testid', locator_value: 'username' }]),
    blankRow('input', '密码输入框', { text: 's3cret' },
             [{ locator_type: 'testid', locator_value: 'password' }]),
    // 首条定位符故意写错：验证回退链在生成的用例里同样生效
    blankRow('click', '登录按钮', {},
             [{ locator_type: 'testid', locator_value: 'submit-not-exist' },
              { locator_type: 'css', locator_value: '#submit' }]),
    blankRow('assert_contains', '', { actual: '欢迎', expected: '欢迎' }),
  ]
  toastInfo('已载入登录示例（第 4 步的首选定位符是故意写错的，用来验证回退链）')
}

// ── 提交 ─────────────────────────────────────────────────
function buildPayload(run: boolean) {
  const elements: any[] = []
  const keyByName = new Map<string, string>()
  let elementSeq = 0

  const payloadActions = rows.value
    .filter((row) => row.action_key)
    .map((row) => {
      let elementKey: string | null = null
      const name = row.element_name.trim()

      if (name) {
        if (!keyByName.has(name)) {
          const key = `el${++elementSeq}`
          keyByName.set(name, key)
          elements.push({
            key, name,
            locators: row.locators
              .filter((l) => l.locator_type && l.locator_value.trim())
              .map((l) => ({ locator_type: l.locator_type, locator_value: l.locator_value.trim() })),
          })
        } else {
          // 同名元素在多行出现：合并定位符（按 type+value 去重）
          const key = keyByName.get(name)!
          const target = elements.find((e) => e.key === key)!
          for (const loc of row.locators) {
            const value = loc.locator_value.trim()
            if (!loc.locator_type || !value) continue
            if (!target.locators.some((x: LocatorRow) =>
              x.locator_type === loc.locator_type && x.locator_value === value)) {
              target.locators.push({ locator_type: loc.locator_type, locator_value: value })
            }
          }
        }
        elementKey = keyByName.get(name)!
      }

      return {
        action_key: row.action_key,
        ...(elementKey ? { element_key: elementKey } : {}),
        params: row.params,
        ...(row.output_var.trim() ? { output_var: row.output_var.trim() } : {}),
      }
    })

  return {
    project: {
      name: projectName.value.trim(), code: projectCode.value.trim(),
      platform, engine_key: engineKey,
    },
    url: url.value.trim(),
    elements,
    actions: payloadActions,
    case: { title: caseTitle.value.trim() },
    suite: { name: suiteName.value.trim() },
    run,
  }
}

function precheck(run: boolean): string | null {
  if (!url.value.trim()) return '请填写网页地址'
  if (!projectCode.value.trim()) return '请填写项目 code'
  if (!caseTitle.value.trim()) return '请填写用例标题'
  if (!suiteName.value.trim()) return '请填写用例集名称'
  if (!rows.value.some((r) => r.action_key)) return '至少需要一条动作'
  for (const [index, row] of rows.value.entries()) {
    if (!row.action_key) continue
    if (needsElement(row) && !row.element_name.trim()) {
      return `第 ${index + 1} 条动作需要填写元素名`
    }
    if (row.element_name.trim() && !row.locators.some((l) => l.locator_type && l.locator_value.trim())) {
      return `第 ${index + 1} 条动作的元素「${row.element_name}」还没有定位符`
    }
  }
  void run
  return null
}

async function submit(run: boolean) {
  const problem = precheck(run)
  if (problem) {
    toastError(problem)
    return
  }
  submitting.value = true
  errorText.value = ''
  result.value = null
  try {
    result.value = await scaffold(buildPayload(run))
    toastSuccess(run ? '已生成并提交执行' : '已生成资产（未执行）')
  } catch (error: any) {
    const body = error?.response?.data?.error
    errorText.value = body
      ? `[${body.code}] ${body.message}`
      : (error?.message ?? '请求失败')
  } finally {
    submitting.value = false
  }
}

function openReport() {
  if (result.value?.execution?.id) {
    void router.push(`/executions/${result.value.execution.id}/report`)
  }
}

const createdCount = computed(() =>
  result.value ? result.value.elements.filter((e: any) => e.created).length : 0)
</script>

<template>
  <div style="display: flex; flex-direction: column; gap: 12px">
    <div class="toolbar">
      <h1>快速接入</h1>
      <span class="tag tag-blue">{{ platform }} / {{ engineKey }}</span>
      <span class="muted">一个网页地址 + 一组动作 → 自动建项目、元素、用例、用例集并执行</span>
      <div class="grow"></div>
      <button class="btn" @click="loadExample">载入登录示例</button>
    </div>

    <!-- 基础信息 -->
    <section class="card">
      <div class="card-header"><h2>1. 基础信息</h2></div>
      <div class="card-body">
        <div class="field">
          <label>网页地址 <span style="color: var(--red)">*</span></label>
          <input v-model="url" class="input mono" placeholder="http://127.0.0.1:8899/login.html" />
          <div class="muted" style="font-size: 12px">
            用它推导执行目标的 base_url（scheme://host:port）；动作里的 navigate 建议写相对路径
          </div>
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1.4fr; gap: 10px">
          <div class="field">
            <label>项目 code <span style="color: var(--red)">*</span></label>
            <input v-model="projectCode" class="input mono" placeholder="demo-web-scaffold" />
            <div class="muted" style="font-size: 12px">幂等键：同一个 code 重复接入会复用项目</div>
          </div>
          <div class="field">
            <label>项目名称 <span style="color: var(--red)">*</span></label>
            <input v-model="projectName" class="input" placeholder="Demo Web 中台" />
          </div>
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px">
          <div class="field">
            <label>用例标题 <span style="color: var(--red)">*</span></label>
            <input v-model="caseTitle" class="input" placeholder="登录主链路" />
          </div>
          <div class="field">
            <label>用例集名称 <span style="color: var(--red)">*</span></label>
            <input v-model="suiteName" class="input" placeholder="冒烟回归" />
          </div>
        </div>
      </div>
    </section>

    <!-- 动作 -->
    <section class="card">
      <div class="card-header">
        <h2>2. 动作清单</h2>
        <div class="toolbar">
          <span class="muted">{{ rows.length }} 条 · 按顺序执行</span>
          <button class="btn btn-sm btn-primary" @click="addRow">添加动作</button>
        </div>
      </div>
      <div class="card-body">
        <div v-for="(row, index) in rows" :key="row.uid" class="action-card">
          <div class="action-head">
            <span class="tag">#{{ index + 1 }}</span>
            <select v-model="row.action_key" class="select" style="width: 260px"
                    @change="onActionChange(row)">
              <option value="">选择动作…</option>
              <option v-for="action in actionOptions" :key="action.action_key"
                      :value="action.action_key">
                {{ action.name }}（{{ action.action_key }}）
              </option>
            </select>
            <span v-if="actionByKey[row.action_key]" class="muted" style="font-size: 12px">
              {{ actionByKey[row.action_key].category }}
            </span>
            <div class="grow"></div>
            <button class="btn btn-sm btn-ghost btn-danger" @click="removeRow(index)">删除</button>
          </div>

          <div v-if="needsElement(row)" class="field">
            <label>元素名 <span style="color: var(--red)">*</span></label>
            <input v-model="row.element_name" class="input" placeholder="如：登录按钮" />

            <div v-if="row.element_name.trim()" style="margin-top: 8px">
              <div v-for="(locator, locIndex) in row.locators" :key="locIndex"
                   style="display: grid; grid-template-columns: 140px 1fr 64px; gap: 8px; margin-bottom: 6px">
                <select v-model="locator.locator_type" class="select">
                  <option value="testid">testid</option>
                  <option value="css">css</option>
                  <option value="xpath">xpath</option>
                  <option value="id">id</option>
                  <option value="text">text</option>
                  <option value="role">role</option>
                  <option value="label">label</option>
                  <option value="placeholder">placeholder</option>
                  <option value="title">title</option>
                  <option value="alt">alt</option>
                </select>
                <input v-model="locator.locator_value" class="input mono" placeholder="定位表达式" />
                <button class="btn btn-sm btn-ghost btn-danger"
                        @click="removeLocator(row, locIndex)">删除</button>
              </div>
              <div class="toolbar">
                <button class="btn btn-sm" @click="addLocator(row)">+ 定位符（回退链）</button>
                <span class="muted" style="font-size: 12px">
                  按顺序回退：第一条失败会试第二条
                </span>
              </div>
            </div>
          </div>

          <SchemaParams v-model="row.params" :schema="schemaOf(row)"
                        :exclude="['output_var']" />

          <div class="field" style="margin-top: 8px">
            <label>输出变量（后续步骤用 <span class="mono">${name}</span> 引用）</label>
            <input v-model="row.output_var" class="input mono" placeholder="可选，如 welcome_text" />
          </div>
        </div>

        <div v-if="!rows.length" class="empty">
          还没有动作。点右上「载入登录示例」快速试一遍，或「添加动作」自己配。
        </div>
      </div>
    </section>

    <!-- 提交 -->
    <section class="card">
      <div class="card-body">
        <div class="toolbar">
          <button class="btn btn-primary" :disabled="submitting" @click="submit(true)">
            {{ submitting ? '生成中…' : '生成并运行' }}
          </button>
          <button class="btn" :disabled="submitting" @click="submit(false)">只生成不运行</button>
          <span class="muted" style="font-size: 12px">
            同一个 code + 同一组元素/用例：重复提交只复用，不会产生重复数据
          </span>
        </div>
      </div>
    </section>

    <!-- 结果 -->
    <section v-if="result" class="card">
      <div class="card-header">
        <h2>3. 生成结果</h2>
        <span class="muted">{{ result.duration_ms }} ms · 新建元素 {{ createdCount }} 个</span>
      </div>
      <div class="card-body">
        <table>
          <thead><tr><th>对象</th><th>id</th><th>结果</th><th>说明</th></tr></thead>
          <tbody>
            <tr>
              <td>项目</td><td class="mono">#{{ result.project.id }}</td>
              <td><span class="tag" :class="result.project.created ? 'tag-green' : ''">
                {{ result.project.created ? '新建' : '复用' }}</span></td>
              <td class="muted mono">{{ result.project.code }}</td>
            </tr>
            <tr>
              <td>执行目标</td><td class="mono">#{{ result.target.id }}</td>
              <td><span class="tag" :class="result.target.created ? 'tag-green' : ''">
                {{ result.target.created ? '新建' : '复用' }}</span></td>
              <td class="muted mono">{{ result.target.base_url }}</td>
            </tr>
            <tr>
              <td>元素</td><td class="mono">{{ result.elements.length }} 个</td>
              <td><span class="tag tag-green">已就绪</span></td>
              <td class="muted">{{ result.elements.map((e: any) => e.name).join('、') }}</td>
            </tr>
            <tr>
              <td>用例</td><td class="mono">#{{ result.case.id }}</td>
              <td><span class="tag" :class="result.case.created ? 'tag-green' : ''">
                {{ result.case.created ? '新建' : '复用' }}</span></td>
              <td class="muted">{{ result.case.step_count }} 个步骤</td>
            </tr>
            <tr>
              <td>用例集</td><td class="mono">#{{ result.suite.id }}</td>
              <td><span class="tag" :class="result.suite.created ? 'tag-green' : ''">
                {{ result.suite.created ? '新建' : '复用' }}</span></td>
              <td class="muted">{{ result.suite.case_count }} 条用例</td>
            </tr>
            <tr>
              <td>执行</td>
              <td class="mono">{{ result.execution ? `#${result.execution.id}` : '—' }}</td>
              <td>
                <span v-if="result.execution" class="tag tag-blue">{{ result.execution.status }}</span>
                <span v-else class="muted">未提交</span>
              </td>
              <td class="muted">
                {{ result.execution ? `用例 ${result.execution.case_count} 条，已入队` : '（只生成不运行）' }}
              </td>
            </tr>
          </tbody>
        </table>

        <div v-if="result.warnings?.length" style="margin-top: 10px">
          <div v-for="(warning, index) in result.warnings" :key="index"
               class="verify-banner verify-warn" style="margin-bottom: 6px">
            {{ warning }}
          </div>
        </div>

        <div class="toolbar" style="margin-top: 12px">
          <button class="btn" @click="router.push('/executions')">查看执行结果</button>
          <button v-if="result.execution" class="btn" @click="openReport">查看报告</button>
          <button class="btn" @click="router.push('/cases')">去用例编排</button>
        </div>
      </div>
    </section>

    <section v-if="errorText" class="card">
      <div class="card-body">
        <div class="verify-banner verify-bad">{{ errorText }}</div>
      </div>
    </section>
  </div>
</template>

<style>
.action-card {
  border: 1px solid var(--border); border-radius: 10px;
  padding: 12px; margin-bottom: 10px; background: #fbfcfe;
}
.action-head { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
</style>
