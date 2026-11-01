<script setup lang="ts">
import draggable from 'vuedraggable'
import type { ElementNode } from '@/api/types'

defineOptions({ name: 'TreeNode' })

const props = defineProps<{
  node: ElementNode
  selectedId: number | null
  expanded: Set<number>
  depth: number
}>()

const emit = defineEmits<{
  select: [id: number]
  toggle: [id: number]
  move: [payload: { id: number; parentId: number; index: number }]
}>()

const isOpen = () => props.expanded.has(props.node.id)

function onChange(event: any) {
  // added = 跨父拖入；moved = 同父重排。两者都交给服务端重算 path/sort
  const payload = event.added ?? event.moved
  if (!payload) return
  emit('move', {
    id: payload.element.id,
    parentId: props.node.id,
    index: payload.newIndex,
  })
}
</script>

<template>
  <div class="tree-node">
    <div class="tree-row" :class="{ active: selectedId === node.id }" @click="emit('select', node.id)">
      <span class="tree-caret" @click.stop="emit('toggle', node.id)">
        {{ node.node_type === 'FOLDER' ? (isOpen() ? '▾' : '▸') : '·' }}
      </span>
      <span class="tree-name" :title="node.path">{{ node.element_name }}</span>
      <span class="tree-badges">
        <span class="badge" :class="{ has: node.locator_count.WEB > 0 }">W{{ node.locator_count.WEB }}</span>
        <span class="badge" :class="{ has: node.locator_count.ANDROID > 0 }">A{{ node.locator_count.ANDROID }}</span>
        <span class="badge" :class="{ has: node.locator_count.IOS > 0 }">I{{ node.locator_count.IOS }}</span>
      </span>
    </div>

    <template v-if="node.node_type === 'FOLDER' && isOpen()">
      <draggable
        v-if="node.children && node.children.length"
        :list="node.children"
        group="elements"
        item-key="id"
        :animation="140"
        ghost-class="drag-ghost"
        class="tree-children"
        @change="onChange"
      >
        <template #item="{ element }">
          <TreeNode
            :node="element"
            :selected-id="selectedId"
            :expanded="expanded"
            :depth="depth + 1"
            @select="emit('select', $event)"
            @toggle="emit('toggle', $event)"
            @move="emit('move', $event)"
          />
        </template>
      </draggable>
      <div v-else class="tree-children">
        <div class="empty" style="padding: 8px 6px; font-size: 12px">空目录</div>
      </div>
    </template>
  </div>
</template>
