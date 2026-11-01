<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  createElement, deleteElement, elementReferences, listElements, moveElement,
} from '@/api'
import type { ElementNode } from '@/api/types'
import AppModal from '@/components/AppModal.vue'
import LocatorPanel from '@/components/LocatorPanel.vue'
import TreeNode from '@/components/TreeNode.vue'
import { toastError, toastSuccess } from '@/components/AppToast'
import { useElementStore } from '@/stores/element'

const store = useElementStore()

const keyword = ref('')
const searchResults = ref<ElementNode[]>([])
const showCreate = ref(false)
const createForm = ref<{ element_name: string; node_type: 'ELEMENT' | 'FOLDER' }>({
  element_name: '', node_type: 'ELEMENT',
})
const deleteTarget = ref<ElementNode | null>(null)
const references = ref<any[]>([])

const parentForCreate = computed(() => {
  const node = store.selectedNode
  if (!node) return 0
  return node.node_type === 'FOLDER' ? node.id : node.parent_id
})

onMounted(async () => {
  await store.init()
})

async function search() {
  if (!store.projectId) return
  if (!keyword.value.trim()) {
    searchResults.value = []
    await store.loadTree()
    return
  }
  const resp = await listElements(store.projectId, { keyword: keyword.value.trim() })
  searchResults.value = resp.items || []
}

async function onMove(payload: { id: number; parentId: number; index: number }) {
  try {
    await moveElement(payload.id, { parent_id: payload.parentId, index: payload.index })
    await store.loadTree()
  } catch {
    // 服务端拒绝（如移到自己的子树）→ 立刻回滚视图
    await store.loadTree()
  }
}

async function submitCreate() {
  if (!store.projectId || !createForm.value.element_name.trim()) return
  await createElement(store.projectId, {
    parent_id: parentForCreate.value,
    element_name: createForm.value.element_name.trim(),
    node_type: createForm.value.node_type,
  })
  showCreate.value = false
  createForm.value = { element_name: '', node_type: 'ELEMENT' }
  await store.loadTree()
  toastSuccess('已创建')
}

async function askDelete(node: ElementNode) {
  deleteTarget.value = node
  const resp = await elementReferences(node.id)
  references.value = (resp.references || []).filter((r: any) => !r.truncated)
}

async function confirmDelete(force: boolean) {
  if (!deleteTarget.value) return
  try {
    await deleteElement(deleteTarget.value.id, force)
    toastSuccess('已删除')
    deleteTarget.value = null
    store.selectedId = null
    await store.loadTree()
  } catch (error: any) {
    if (error?.response?.data?.error?.code === 'ELEMENT_REFERENCED') {
      references.value = error.response.data.error.detail.references || []
    } else {
      toastError('删除失败')
    }
  }
}

const counts = computed(() => store.stats?.coverage ?? {})
</script>

<template>
  <div style="display: flex; flex-direction: column; gap: 12px; height: 100%">
    <div class="toolbar">
      <h1>元素库</h1>
      <select v-model.number="store.projectId" class="select" style="width: 220px" @change="store.loadTree()">
        <option v-for="project in store.projects" :key="project.id" :value="project.id">
          {{ project.name }}（{{ project.platform }} / {{ project.engine_key }}）
        </option>
      </select>
      <span v-if="store.stats" class="tag">
        元素 {{ store.stats.total_elements }} ·
        Web 缺配 {{ counts.WEB?.missing ?? 0 }}
      </span>
      <div class="grow"></div>
      <input
        v-model="keyword"
        class="input"
        style="width: 220px"
        placeholder="搜索元素名…"
        @keyup.enter="search"
        @input="!keyword && search()"
      />
      <button class="btn" @click="store.expandAll()">展开全部</button>
      <button class="btn" @click="store.loadTree()">刷新</button>
      <button class="btn" @click="createForm.node_type = 'FOLDER'; showCreate = true">新建目录</button>
      <button class="btn btn-primary" @click="createForm.node_type = 'ELEMENT'; showCreate = true">
        新建元素
      </button>
    </div>

    <div v-if="!store.projects.length" class="card">
      <div class="card-body empty">
        还没有项目。先执行 <span class="mono">python -m app.cli seed-demo</span> 生成演示项目。
      </div>
    </div>

    <div v-else class="library" style="min-height: 0">
      <!-- 左：树 / 搜索结果 -->
      <section class="card library-side">
        <div class="card-header">
          <h2>{{ keyword && searchResults.length ? '搜索结果' : '元素树' }}</h2>
          <span class="muted" style="font-size: 12px">拖拽可排序 / 换父</span>
        </div>
        <div class="tree-scroll">
          <template v-if="keyword && searchResults.length">
            <div
              v-for="item in searchResults"
              :key="item.id"
              class="tree-row"
              @click="store.selectNode(item.id)"
            >
              <span class="tree-caret">{{ item.node_type === 'FOLDER' ? '▸' : '·' }}</span>
              <span class="tree-name">
                <span class="muted" style="font-size: 11px">
                  {{ (item.path_names || []).join(' / ') }} /
                </span>
                {{ item.element_name }}
              </span>
            </div>
          </template>
          <template v-else>
            <TreeNode
              v-for="node in store.tree"
              :key="node.id"
              :node="node"
              :selected-id="store.selectedId"
              :expanded="store.expanded"
              :depth="0"
              @select="store.selectNode"
              @toggle="store.toggle"
              @move="onMove"
            />
            <div v-if="!store.tree.length && !store.loading.tree" class="empty">
              还没有元素。点右上「新建目录」开始。
            </div>
          </template>
        </div>
      </section>

      <!-- 右：详情 + 定位符 -->
      <div class="library-main">
        <template v-if="store.selectedNode">
          <section class="card">
            <div class="card-header">
              <div>
                <h2>{{ store.selectedNode.element_name }}</h2>
                <div class="muted" style="font-size: 12px; margin-top: 3px">
                  <span class="mono">{{ store.selectedNode.path }}</span>
                  · {{ store.selectedNode.node_type }}
                </div>
              </div>
              <div class="toolbar">
                <span class="tag">{{ store.coverage.WEB || 0 }} Web</span>
                <span class="tag">{{ store.coverage.ANDROID || 0 }} Android</span>
                <span class="tag">{{ store.coverage.IOS || 0 }} iOS</span>
                <button class="btn btn-danger" @click="askDelete(store.selectedNode)">删除</button>
              </div>
            </div>
            <div v-if="store.selectedNode.memo" class="card-body muted" style="padding-top: 10px">
              {{ store.selectedNode.memo }}
            </div>
          </section>

          <LocatorPanel
            v-if="store.selectedNode.node_type === 'ELEMENT'"
            :element-id="store.selectedNode.id"
            :groups="store.groups"
            :dict="store.dict"
            :verify-result="store.verifyResult"
            :verifying="store.loading.verify"
            @changed="store.refreshSelected()"
            @verify="store.verify(store.selectedNode!.id, $event.platform, $event.engineKey, $event.drafts)"
          />
          <section v-else class="card">
            <div class="card-body empty">目录节点不能配置定位符。请在其下新建元素。</div>
          </section>
        </template>
        <section v-else class="card">
          <div class="card-body empty">从左侧选择一个元素或目录。</div>
        </section>
      </div>
    </div>

    <AppModal
      v-if="showCreate"
      :title="createForm.node_type === 'FOLDER' ? '新建目录' : '新建元素'"
      @close="showCreate = false"
      @confirm="submitCreate"
    >
      <div class="field">
        <label>挂在</label>
        <input class="input" :value="`元素 ID ${parentForCreate}${parentForCreate ? '' : '（根）'}`" disabled />
      </div>
      <div class="field">
        <label>名称</label>
        <input v-model="createForm.element_name" class="input" placeholder="如：登录按钮" autofocus />
      </div>
    </AppModal>

    <AppModal
      v-if="deleteTarget"
      :title="`删除「${deleteTarget.element_name}」`"
      confirm-text="确认删除"
      danger
      @close="deleteTarget = null"
      @confirm="confirmDelete(true)"
    >
      <div v-if="references.length">
        <p>该元素被 {{ references.length }} 个用例步骤引用：</p>
        <ul style="margin: 8px 0 0 18px; padding: 0">
          <li v-for="(ref, idx) in references.slice(0, 10)" :key="idx">
            用例 #{{ ref.case_id }} 「{{ ref.title }}」第 {{ ref.step_seq }} 步 <span class="mono">{{ ref.action_key }}</span>
          </li>
        </ul>
        <p class="muted" style="margin-top: 10px">删除后这些步骤将无法执行。</p>
      </div>
      <p v-else>该元素没有引用，可以安全删除。</p>
    </AppModal>
  </div>
</template>
