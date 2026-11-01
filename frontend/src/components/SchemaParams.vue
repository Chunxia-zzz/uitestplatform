<script setup lang="ts">
/**
 * 按动作字典的 params_schema 生成表单（M3.2 的 StepEditor 与 M3.4 的 Scaffold 共用）。
 *
 * 抽成组件的理由：两处都要"选动作 → 出参数"，各写一套必然漂移 ——
 * 一边加了 enum 支持、另一边没加，用户会觉得同一个动作在两个页面表现不同。
 */
import { computed, ref } from 'vue'

const props = defineProps<{
  schema: { properties?: Record<string, any>; required?: string[] } | null
  modelValue: Record<string, any>
  /** 需要单独用输入框展示的字段（如 output_var） */
  exclude?: string[]
}>()

const emit = defineEmits<{ 'update:modelValue': [Record<string, any>] }>()

interface Field {
  key: string
  type: string
  enumValues: unknown[] | null
  description: string
  required: boolean
}

const fields = computed<Field[]>(() => {
  const schema = props.schema
  const properties = schema?.properties ?? {}
  const required = new Set(schema?.required ?? [])
  const excluded = new Set(props.exclude ?? [])
  return Object.entries(properties)
    .filter(([key]) => !excluded.has(key))
    .map(([key, spec]: [string, any]) => ({
      key,
      type: String(spec.type ?? 'string'),
      enumValues: Array.isArray(spec.enum) ? spec.enum : null,
      description: typeof spec.description === 'string' ? spec.description : '',
      required: required.has(key),
    }))
})

const jsonErrors = ref<Record<string, string>>({})

function valueOf(key: string): any {
  return props.modelValue?.[key]
}

function setValue(key: string, value: any) {
  const next = { ...(props.modelValue ?? {}) }
  if (value === '' || value === null || value === undefined) {
    delete next[key]
  } else {
    next[key] = value
  }
  emit('update:modelValue', next)
}

/** array / object 参数用 JSON 文本编辑；解析成功才写回，失败保留原文并提示。 */
function setJson(key: string, text: string) {
  if (!text.trim()) {
    delete jsonErrors.value[key]
    setValue(key, null)
    return
  }
  try {
    setValue(key, JSON.parse(text))
    delete jsonErrors.value[key]
  } catch {
    jsonErrors.value = { ...jsonErrors.value, [key]: 'JSON 格式不合法' }
  }
}

function jsonText(key: string): string {
  const value = valueOf(key)
  return value === undefined ? '' : JSON.stringify(value, null, 2)
}

defineExpose({
  hasErrors: () => Object.keys(jsonErrors.value).length > 0,
})
</script>

<template>
  <div class="schema-params">
    <div v-for="field in fields" :key="field.key" class="field">
      <label>
        {{ field.key }}
        <span v-if="field.required" style="color: var(--red)">*</span>
        <span class="muted" style="font-weight: 400; font-size: 12px">（{{ field.type }}）</span>
      </label>

      <select
        v-if="field.enumValues"
        class="select"
        :value="valueOf(field.key) ?? ''"
        @change="setValue(field.key, ($event.target as HTMLSelectElement).value || null)"
      >
        <option value="">（不传）</option>
        <option v-for="option in field.enumValues" :key="String(option)" :value="option">
          {{ option }}
        </option>
      </select>

      <label v-else-if="field.type === 'boolean'" style="font-weight: 400">
        <input
          type="checkbox"
          :checked="!!valueOf(field.key)"
          @change="setValue(field.key, ($event.target as HTMLInputElement).checked)"
        />
        启用
      </label>

      <input
        v-else-if="field.type === 'integer' || field.type === 'number'"
        class="input"
        type="number"
        :value="valueOf(field.key) ?? ''"
        @input="setValue(field.key, ($event.target as HTMLInputElement).value === ''
          ? null : Number(($event.target as HTMLInputElement).value))"
      />

      <textarea
        v-else-if="field.type === 'array' || field.type === 'object'"
        class="input mono"
        rows="3"
        :value="jsonText(field.key)"
        @change="setJson(field.key, ($event.target as HTMLTextAreaElement).value)"
      ></textarea>

      <input
        v-else
        class="input"
        :value="valueOf(field.key) ?? ''"
        @input="setValue(field.key, ($event.target as HTMLInputElement).value)"
      />

      <div v-if="jsonErrors[field.key]" style="color: var(--red); font-size: 12px">
        {{ jsonErrors[field.key] }}
      </div>
      <div v-else-if="field.description" class="muted" style="font-size: 12px">
        {{ field.description }}
      </div>
    </div>
    <div v-if="!fields.length" class="muted" style="font-size: 12px">该动作没有参数</div>
  </div>
</template>
