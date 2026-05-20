<template>
  <Dialog
    v-model="show"
    :options="{
      title,
      message,
      actions: [
        { label: 'Cancel', variant: 'subtle', onClick: close },
        { label: confirmLabel, variant: variant, onClick: confirm, loading: loading },
      ],
    }"
  />
</template>

<script setup>
import { computed } from 'vue'
import { Dialog } from 'frappe-ui'

const props = defineProps({
  modelValue: Boolean,
  title: { type: String, default: 'Confirm' },
  message: { type: String, default: 'Are you sure?' },
  confirmLabel: { type: String, default: 'Confirm' },
  variant: { type: String, default: 'solid' },
  loading: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'confirm'])

const show = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

function close() { show.value = false }
function confirm() { emit('confirm') }
</script>
