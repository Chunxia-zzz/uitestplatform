<script setup lang="ts">
import draggable from 'vuedraggable'
import { computed, ref, watch } from 'vue'

import {
  createLocator, deleteLocator, reorderLocators, setPrimaryLocator, updateLocator,
} from '@/api'
import type { LocatorGroup, LocatorTypeDict, Platform, VerifyResponse } from '@/api/types'
import { toastError, toastInfo, toastSuccess } from '@/components/AppToast'

const props = defineProps<{
  elementId: number
  groups: LocatorGroup[]
  dict: LocatorTypeDict | null
  verifyResult: VerifyResponse | null
  verifying: boolean
}>()

const emit = defineEmits<{ changed: []; verify: [payload: {
  platform: string; engineKey: string; drafts: { locator_type: string; locator_value: string }[]
}] }>()

const platforms: Platform[] = ['WEB', 'ANDROID', 'IOS']
const active = ref<Platform>('WEB')

const localGroups = ref<LocatorGroup[]>([])
watch(() => props.groups, (value) => {
  localGroups.value = JSON.parse(JSON.stringify(value || []))
}, { immediate: true, deep: true })

const platformDict = computed(() => props.dict?.platforms?.[active.value] ?? null)
const engineOptions = computed(() => {
  const all = platformDict.value?.engines ?? []
  return ['*', ...all]
})

const visibleGroups = computed(() =>
  localGroups.value.filter((g) => g.platform === active.value))

const totalFor = (platform: Platform) =>
  localGroups.value.filter((g) => g.platform === platform)
    .reduce((sum, g) => sum + g.items.length, 0)

// 新增表单
const engineKey = ref('*')
const locatorType = ref('')
const locatorValue = ref('')
const drafts = ref<{ engine_key: string; locator_type: string; locator_value: string }[]>([])

const typeOptions = computed(() => {
  const types = platformDict.value?.types ?? []
  if (engineKey.value === '*') {
    // 通配只能用"全部引擎都支持"的语义类型 —— 与服务端第 3 层校验一致
    return types.filter((t) => t.engines.length === (platformDict.value?.engines?.length ?? 0))
  }
  return types.filter((t) => t.engines.includes(engineKey.value))
})

watch([active, engineKey], () => {
  if (!typeOptions.value.some((t) => t.key === locatorType.value)) {
    locatorType.value = typeOptions.value[0]?.key ?? ''
  }
}, { immediate: true })

const currentSpec = computed(() =>
  typeOptions.value.find((t) => t.key === locatorType.value) ?? null)

function verdictOf(item: any): string {
  if (item.probe_detail?.verdict) return item.probe_detail.verdict
  return item.status
}

function addDraft() {
  if (!locatorType.value || !locatorValue.value.trim()) return
  drafts.value.push({
    engine_key: engineKey.value,
    locator_type: locatorType.value,
    locator_value: locatorValue.value.trim(),
  })
  locatorValue.value = ''
}

async function saveDraft(index: number) {
  const draft = drafts.value[index]
  await createLocator(props.elementId, {
    platform: active.value,
    engine_key: draft.engine_key,
    locator_type: draft.locator_type,
    locator_value: draft.locator_value,
  })
  drafts.value.splice(index, 1)
  toastSuccess('已保存（建议点「验证」确认能命中）')
  emit('changed')
}

async function saveAllDrafts() {
  for (let i = drafts.value.length - 1; i >= 0; i -= 1) {
    await saveDraft(i)
  }
}

function doVerify() {
  const group = visibleGroups.value[0]
  emit('verify', {
    platform: active.value,
    engineKey: group?.engine_key ?? engineKey.value,
    drafts: drafts.value.map((d) => ({
      locator_type: d.locator_type, locator_value: d.locator_value,
    })),
  })
}

async function onReorder(group: LocatorGroup) {
  const ids = group.items.map((i) => i.id)
  await reorderLocators(props.elementId, group.platform, group.engine_key, ids)
  toastInfo('顺序已保存（回退链随之改变）')
  emit('changed')
}

// 行内编辑（GAP-26）：改一个定位符值不该走"删了重建"—— 那样会丢 priority 与验证历史
const editingId = ref<number | null>(null)
const editingValue = ref('')

function startEdit(item: any) {
  editingId.value = item.id
  editingValue.value = item.locator_value
}

function cancelEdit() {
  editingId.value = null
  editingValue.value = ''
}

async function commitEdit(item: any) {
  const value = editingValue.value.trim()
  if (!value) {
    toastError('定位符值不能为空')
    return
  }
  if (value === item.locator_value) {
    cancelEdit()
    return
  }
  try {
    await updateLocator(item.id, { locator_value: value })
    toastSuccess('已保存（状态回到未验证）')
    cancelEdit()
    emit('changed')
  } catch {
    // http 拦截器已提示；保留编辑态让用户改
  }
}

/** Esc 先清 editingId，随后元素移除会触发 blur —— 这里必须再判断一次。 */
function onEditBlur(item: any) {
  if (editingId.value === item.id) void commitEdit(item)
}

async function toggleEnabled(item: any) {
  await updateLocator(item.id, { enabled: !item.enabled })
  emit('changed')
}

async function makePrimary(item: any) {
  await setPrimaryLocator(item.id)
  toastInfo('已设为首选（仅展示标记，执行仍按顺序）')
  emit('changed')
}

async function remove(item: any) {
  if (!window.confirm(`删除定位符 ${item.locator_type}=${item.locator_value}？`)) return
  await deleteLocator(item.id)
  emit('changed')
}

function summarize() {
  const v = props.verifyResult
  if (!v) return null
  return v.summary
}
</script>

<template>
  <section class="card">
    <div class="card-header">
      <div class="tabs">
        <button
          v-for="platform in platforms"
          :key="platform"
          class="tab"
          :class="{ active: active === platform }"
          @click="active = platform"
        >
          {{ platform }}
          <span class="tag" :class="{ 'tag-blue': totalFor(platform) > 0 }">{{ totalFor(platform) }}</span>
        </button>
      </div>
      <div class="toolbar">
        <button class="btn" :disabled="verifying" @click="doVerify">
          {{ verifying ? '验证中…' : '验证当前端' }}
        </button>
      </div>
    </div>

    <div class="card-body" style="padding: 0">
      <!-- 验证结果条：四态语义必须与后端一致（MULTIPLE 只警告） -->
      <div v-if="verifyResult" style="padding: 12px 14px 0">
        <div
          class="verify-banner"
          :class="verifyResult.verdict === 'ALL_VALID' ? 'verify-ok'
            : verifyResult.verdict === 'ALL_INVALID' ? 'verify-bad' : 'verify-warn'"
        >
          <strong>
            <template v-if="verifyResult.verdict === 'ALL_VALID'">全部有效</template>
            <template v-else-if="verifyResult.verdict === 'ALL_INVALID'">全部未命中</template>
            <template v-else>存在问题</template>
            <span class="muted" style="font-weight: 400">
              · {{ verifyResult.url }} · {{ verifyResult.duration_ms }}ms
            </span>
          </strong>
          <div>
            有效 {{ summarize()?.valid }} · 命中多个 {{ summarize()?.multiple }} ·
            未命中 {{ summarize()?.none }} · 异常 {{ summarize()?.error }}
          </div>
          <div v-for="(item, idx) in verifyResult.results.filter(r => r.verdict !== 'VALID')" :key="idx" class="mono" style="font-size: 12px">
            {{ item.verdict }} · {{ item.locator_type }}={{ item.locator_value }}
            → 命中 {{ item.matched }} 个（{{ item.duration_ms }}ms）
            <span v-if="item.error">· {{ item.error }}</span>
          </div>
        </div>
      </div>

      <div v-for="group in visibleGroups" :key="group.platform + group.engine_key">
        <div class="muted" style="padding: 10px 14px 2px; font-size: 12px">
          engine_key = <span class="mono">{{ group.engine_key }}</span>
          <span v-if="group.primary_id"> · 首选 #{{ group.primary_id }}</span>
        </div>

        <draggable
          :list="group.items"
          item-key="id"
          handle=".drag-handle"
          :animation="130"
          ghost-class="drag-ghost"
          @end="onReorder(group)"
        >
          <template #item="{ element: item }">
            <div class="locator-row">
              <span class="drag-handle">⠿</span>
              <span class="dot" :class="`dot-${verdictOf(item)}`" :title="item.status"></span>
              <span class="tag">{{ item.locator_type }}</span>
              <input
                v-if="editingId === item.id"
                v-model="editingValue"
                class="input mono locator-edit"
                autofocus
                @keyup.enter="commitEdit(item)"
                @keyup.esc="cancelEdit"
                @blur="onEditBlur(item)"
              />
              <span
                v-else
                class="locator-value mono"
                :title="`${item.locator_value}（双击编辑）`"
                @dblclick="startEdit(item)"
              >{{ item.locator_value }}</span>
              <span class="muted" style="font-size: 12px">
                <template v-if="item.probe_detail?.matched !== undefined">
                  命中 {{ item.probe_detail.matched }}
                </template>
                <template v-else>未验证</template>
              </span>
              <span class="toolbar" style="justify-content: flex-end">
                <button class="btn btn-sm btn-ghost" title="编辑值" @click="startEdit(item)">✎</button>
                <button class="btn btn-sm btn-ghost" title="设为首选" @click="makePrimary(item)">★</button>
                <button class="btn btn-sm btn-ghost" :title="item.enabled ? '禁用' : '启用'" @click="toggleEnabled(item)">
                  {{ item.enabled ? '👁' : '🚫' }}
                </button>
                <button class="btn btn-sm btn-ghost btn-danger" title="删除" @click="remove(item)">✕</button>
              </span>
            </div>
          </template>
        </draggable>

        <div v-if="!group.items.length" class="empty">该组还没有定位符</div>
      </div>

      <div v-if="!visibleGroups.length" class="empty">
        还没有 {{ active }} 端的定位符。在下面添加第一条。
      </div>

      <!-- 草稿区 -->
      <div v-if="drafts.length" style="padding: 10px 14px; border-top: 1px dashed var(--border)">
        <h3>未保存（可先验证再保存）</h3>
        <div v-for="(draft, idx) in drafts" :key="idx" class="locator-row" style="grid-template-columns: 18px 14px 92px 1fr 120px 150px">
          <span></span>
          <span class="dot dot-UNVERIFIED"></span>
          <span class="tag">{{ draft.locator_type }}</span>
          <span class="locator-value mono">{{ draft.locator_value }}</span>
          <span class="muted" style="font-size: 12px">{{ draft.engine_key }}</span>
          <span class="toolbar" style="justify-content: flex-end">
            <button class="btn btn-sm" @click="saveDraft(idx)">保存</button>
            <button class="btn btn-sm btn-ghost btn-danger" @click="drafts.splice(idx, 1)">✕</button>
          </span>
        </div>
        <div style="margin-top: 8px">
          <button class="btn btn-sm" @click="saveAllDrafts">全部保存</button>
        </div>
      </div>

      <!-- 新增 -->
      <div style="padding: 12px 14px; border-top: 1px solid var(--border); background: #fafbfc">
        <div style="display: grid; grid-template-columns: 130px 150px 1fr auto auto; gap: 8px">
          <select v-model="engineKey" class="select">
            <option v-for="engine in engineOptions" :key="engine" :value="engine">
              {{ engine === '*' ? '* 全引擎通用' : engine }}
            </option>
          </select>
          <select v-model="locatorType" class="select">
            <option v-for="type in typeOptions" :key="type.key" :value="type.key">{{ type.label }}</option>
          </select>
          <input
            v-model="locatorValue"
            class="input mono"
            :placeholder="currentSpec?.example || '定位表达式'"
            @keyup.enter="addDraft"
          />
          <button class="btn" @click="addDraft">加入草稿</button>
          <button class="btn btn-primary" @click="addDraft(); doVerify()">先验证</button>
        </div>
        <div v-if="currentSpec" class="muted" style="font-size: 12px; margin-top: 6px">
          {{ currentSpec.note }} · 支持引擎：{{ currentSpec.engines.join(' / ') }}
        </div>
        <div v-if="!typeOptions.length" class="muted" style="font-size: 12px; margin-top: 6px">
          通配 <span class="mono">*</span> 下没有"全引擎通用"的类型。请选择具体引擎，或改用 resource_id 这类通用语义。
        </div>
      </div>
    </div>
  </section>
</template>
