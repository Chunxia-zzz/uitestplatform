<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { engineCapabilities, listActions, listEngines } from '@/api'

const engines = ref<any[]>([])
const selected = ref<string | null>(null)
const capabilities = ref<any>(null)
const actions = ref<any[]>([])

onMounted(async () => {
  const resp = await listEngines()
  engines.value = resp.items
  if (engines.value.length) await select(engines.value[0].key)
  const catalog = await listActions()
  actions.value = catalog.items
})

async function select(key: string) {
  selected.value = key
  capabilities.value = await engineCapabilities(key)
}
</script>

<template>
  <div style="display: flex; flex-direction: column; gap: 12px">
    <div class="toolbar">
      <h1>引擎与能力</h1>
      <span class="muted">能力的唯一事实来源是 CAPABILITY_MATRIX，启动时与动作字典双向校验</span>
    </div>

    <section class="card">
      <div class="card-header"><h2>已注册引擎</h2></div>
      <table>
        <thead>
          <tr><th>引擎</th><th>平台</th><th>实现状态</th><th>动作数</th><th></th></tr>
        </thead>
        <tbody>
          <tr v-for="engine in engines" :key="engine.key" @click="select(engine.key)" style="cursor: pointer">
            <td class="mono">{{ engine.key }}</td>
            <td>{{ engine.platforms.join(' / ') }}</td>
            <td>
              <span class="tag" :class="engine.implemented ? 'tag-green' : 'tag-amber'">
                {{ engine.implemented ? '已实现' : '桩（计划 M4）' }}
              </span>
            </td>
            <td>{{ engine.action_count }}</td>
            <td class="muted">{{ selected === engine.key ? '当前' : '' }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-if="capabilities" class="card">
      <div class="card-header">
        <h2>{{ capabilities.label }} 的动作清单</h2>
        <span class="mono muted">{{ capabilities.action_count }} 个</span>
      </div>
      <div class="card-body" style="display: flex; flex-wrap: wrap; gap: 6px">
        <span v-for="key in capabilities.actions" :key="key" class="tag">{{ key }}</span>
      </div>
    </section>

    <section class="card">
      <div class="card-header">
        <h2>动作字典（{{ actions.length }} 条）</h2>
        <span class="muted">平台内建动作 engines 为空</span>
      </div>
      <div style="max-height: 420px; overflow: auto">
        <table>
          <thead>
            <tr><th>action_key</th><th>中文名</th><th>分类</th><th>平台</th><th>引擎</th><th>元素</th></tr>
          </thead>
          <tbody>
            <tr v-for="action in actions" :key="action.action_key">
              <td class="mono">{{ action.action_key }}</td>
              <td>{{ action.name }}</td>
              <td><span class="tag">{{ action.category }}</span></td>
              <td class="muted">{{ (action.platforms || []).join(',') }}</td>
              <td class="muted">{{ (action.engines || []).length ? action.engines.join(',') : '内建' }}</td>
              <td>{{ action.requires_element ? '需要' : '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>
