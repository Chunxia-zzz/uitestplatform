<script setup lang="ts">
const props = defineProps<{
  title: string
  confirmText?: string
  danger?: boolean
  /** M3.2：步骤表单字段多，需要更宽的弹窗 */
  width?: string
}>()
const emit = defineEmits<{ close: []; confirm: [] }>()
</script>

<template>
  <div class="modal-mask" @click.self="emit('close')">
    <div class="modal" :style="props.width ? { width: props.width, maxWidth: '94vw' } : undefined">
      <div class="modal-head">{{ props.title }}</div>
      <div class="modal-body"><slot /></div>
      <div class="modal-foot">
        <button class="btn" @click="emit('close')">取消</button>
        <button class="btn" :class="props.danger ? 'btn-danger' : 'btn-primary'" @click="emit('confirm')">
          {{ props.confirmText || '确定' }}
        </button>
      </div>
    </div>
  </div>
</template>
