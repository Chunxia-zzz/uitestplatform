<script setup lang="ts">
/**
 * 元素扫描（M3.5 / D28）：输入 URL → 扫描页面元素 → 人工勾选确认 → 落库。
 *
 * 设计原则（D28）：
 * * 扫描只读，不落库；只有"导入"才写元素库。
 * * 默认只勾选 strong/medium，弱等级不默认勾（降低误导入）。
 * * 导入可改名、可删定位符。
 */
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import { importScanCandidates, listProjects, scanPage } from '@/api'
import type { Project, ScanCandidate, ScanImportResult, ScanResult } from '@/api/types'
import { toastError, toastSuccess } from '@/components/AppToast'

const router = useRouter()

const projects = ref<Project[]>([])
const projectId = ref<number | null>(null)
const url = ref('')
const scanning = ref(false)
const importing = ref(false)

const result = ref<ScanResult | null>(null)
const importResult = ref<ScanImportResult | null>(null)
const errorText = ref('')

// 候选勾选状态：key -> 是否勾选
const selected = ref<Record<string, boolean>>({})
// 改名：key -> 新名
const renamed = ref<Record<string, string>>({})
// 每个候选保留哪些定位符（默认全保留）
const keptLocators = ref<Record<string, boolean[]>>({})

const currentProject = computed(() => projects.value.find((p) => p.id === projectId.value) ?? null)

async function loadProjects() {
  const resp = await listProjects()
  projects.value = resp.items
  if (projects.value.length && projectId.value === null) {
    projectId.value = projects.value[0].id
  }
}

loadProjects()

const strengthLabel = (s: string) =>
  s === 'strong' ? '强' : s === 'medium' ? '中' : '弱'

function toggleCandidate(candidate: ScanCandidate) {
  selected.value[candidate.key] = !selected.value[candidate.key]
}

function onScan() {
  // 初始化勾选：默认勾 strong/medium
  if (result.value) {
    for (const c of result.value.candidates) {
      selected.value[c.key] = c.strength !== 'weak'
      renamed.value[c.key] = c.name
      keptLocators.value[c.key] = c.locators.map(() => true)
    }
  }
}

async function scan() {
  if (!projectId.value || !url.value.trim()) {
    toastError('请选择项目并填写 URL')
    return
  }
  scanning.value = true
  errorText.value = ''
  result.value = null
  importResult.value = null
  try {
    result.value = await scanPage(projectId.value, { url: url.value.trim() })
    onScan()
  } catch (error: any) {
    const body = error?.response?.data?.error
    errorText.value = body ? `[${body.code}] ${body.message}` : (error?.message ?? '扫描失败')
  } finally {
    scanning.value = false
  }
}

const chosen = computed<ScanCandidate[]>(() =>
  result.value ? result.value.candidates.filter((c) => selected.value[c.key]) : [])

async function importSelected() {
  if (!projectId.value || !chosen.value.length) {
    toastError('请至少勾选一个元素')
    return
  }
  importing.value = true
  importResult.value = null
  try {
    importResult.value = await importScanCandidates(projectId.value, {
      candidates: chosen.value.map((c) => ({
        name: (renamed.value[c.key] || c.name).trim() || c.name,
        locators: c.locators
          .filter((_, index) => keptLocators.value[c.key]?.[index] !== false)
          .map((l) => ({ locator_type: l.locator_type, locator_value: l.locator_value })),
      })),
    })
    toastSuccess(`已导入 ${importResult.value.created.length} 个元素`)
  } catch (error: any) {
    const body = error?.response?.data?.error
    errorText.value = body ? `[${body.code}] ${body.message}` : (error?.message ?? '导入失败')
  } finally {
    importing.value = false
  }
}

function goElements() {
  void router.push('/elements')
}
</script>

<template>
  <div style="display: flex; flex-direction: column; gap: 12px">
    <div class="toolbar">
      <h1>元素扫描</h1>
      <span class="tag tag-blue">自动扫描 · 人工确认落库</span>
      <span class="muted">输入 URL 扫描页面元素，勾选有效的导入元素库</span>
      <div class="grow"></div>
    </div>

    <!-- 1. 扫描 -->
    <section class="card">
      <div class="card-body">
        <div style="display: grid; grid-template-columns: 220px 1fr auto; gap: 10px">
          <select v-model.number="projectId" class="select">
            <option :value="null">选择项目…</option>
            <option v-for="project in projects" :key="project.id" :value="project.id">
              {{ project.name }}（{{ project.platform }}/{{ project.engine_key }}）
            </option>
          </select>
          <input v-model="url" class="input mono" placeholder="http://127.0.0.1:8899/todo.html"
                 @keyup.enter="scan" />
          <button class="btn btn-primary" :disabled="scanning" @click="scan">
            {{ scanning ? '扫描中…' : '开始扫描' }}
          </button>
        </div>
        <div v-if="currentProject && currentProject.platform !== 'WEB'" class="muted" style="font-size: 12px; margin-top: 8px">
          注意：当前项目是 {{ currentProject.platform }} 端，扫描暂只支持 Web（Appium/u2 仍是桩，见 M4）。
        </div>
      </div>
    </section>

    <!-- 2. 候选清单 -->
    <section v-if="result" class="card">
      <div class="card-header">
        <h2>候选元素（{{ result.candidates.length }} 个，已勾选 {{ chosen.length }}）</h2>
        <div class="toolbar">
          <span class="muted">
            强 {{ result.stats.strong }} · 中 {{ result.stats.medium }} · 弱 {{ result.stats.weak }}
            · 跳过 {{ result.stats.skipped }}
          </span>
        </div>
      </div>
      <div class="card-body">
        <div v-for="warning in result.warnings" :key="warning"
             class="verify-banner verify-warn" style="margin-bottom: 6px">{{ warning }}</div>

        <table>
          <thead>
            <tr>
              <th style="width: 36px">选</th>
              <th style="width: 80px">标签</th>
              <th>元素名</th>
              <th>主定位符</th>
              <th style="width: 56px">稳定</th>
              <th style="width: 120px">文本</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="candidate in result.candidates" :key="candidate.key"
                :class="{ 'row-disabled': !selected[candidate.key] }">
              <td>
                <input type="checkbox" :checked="!!selected[candidate.key]"
                       @change="toggleCandidate(candidate)" />
              </td>
              <td class="mono">{{ candidate.tag }}</td>
              <td>
                <input v-model="renamed[candidate.key]" class="input"
                       :class="selected[candidate.key] ? '' : 'muted'" style="max-width: 240px" />
              </td>
              <td class="mono" style="font-size: 12px">
                <template v-for="(locator, index) in candidate.locators" :key="index">
                  <label style="font-weight: 400; margin-right: 10px">
                    <input type="checkbox" v-model="keptLocators[candidate.key][index]"
                           style="margin-right: 3px" />
                    {{ locator.locator_type }}={{ locator.locator_value }}
                    <span v-if="locator.primary" class="tag tag-blue" style="font-size: 11px">主</span>
                  </label>
                </template>
              </td>
              <td>
                <span class="tag"
                      :class="candidate.strength === 'strong' ? 'tag-green'
                        : candidate.strength === 'medium' ? '' : 'tag-amber'">
                  {{ strengthLabel(candidate.strength) }}
                </span>
              </td>
              <td class="muted" style="font-size: 12px">
                <span :title="candidate.text || ''"
                      style="display: inline-block; max-width: 110px; overflow: hidden;
                             text-overflow: ellipsis; white-space: nowrap; vertical-align: bottom">
                  {{ candidate.text ? candidate.text.slice(0, 40) : '—' }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>

        <div class="toolbar" style="margin-top: 12px">
          <span class="muted">默认勾选「强/中」，弱等级需手动勾选</span>
          <div class="grow"></div>
          <button class="btn btn-primary" :disabled="importing || !chosen.length" @click="importSelected">
            {{ importing ? '导入中…' : `导入选中（${chosen.length}）` }}
          </button>
        </div>
      </div>
    </section>

    <!-- 3. 导入结果 -->
    <section v-if="importResult" class="card">
      <div class="card-header"><h2>导入结果</h2></div>
      <div class="card-body">
        <div v-if="importResult.created.length" class="verify-banner verify-ok" style="margin-bottom: 8px">
          成功导入 {{ importResult.created.length }} 个元素
        </div>
        <div v-for="item in importResult.created" :key="item.element_id" class="mono" style="font-size: 12px; padding: 2px 0">
          ✓ {{ item.name }} → 元素 #{{ item.element_id }}（定位符 {{ item.locator_ids.length }} 条）
        </div>
        <div v-for="item in importResult.failed" :key="item.name + item.code" style="color: var(--red); font-size: 12px; padding: 2px 0">
          ✕ {{ item.name }}：[{{ item.code }}] {{ item.message }}
        </div>
        <button class="btn" style="margin-top: 12px" @click="goElements">去元素库查看</button>
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
.row-disabled { opacity: 0.5; }
</style>
