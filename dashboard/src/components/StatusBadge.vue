<template>
  <span
    :class="[
      'inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium',
      tone,
    ]"
  >
    <span class="h-1.5 w-1.5 rounded-full" :class="dot" />
    {{ status }}
  </span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  status: { type: String, required: true },
})

const tones = {
  Running:    ['bg-green-50 text-green-700',  'bg-green-500'],
  Active:     ['bg-green-50 text-green-700',  'bg-green-500'],
  Stopped:    ['bg-gray-100 text-gray-700',   'bg-gray-400'],
  Pending:    ['bg-blue-50 text-blue-700',    'bg-blue-500'],
  Starting:   ['bg-blue-50 text-blue-700',    'bg-blue-500'],
  Building:   ['bg-amber-50 text-amber-800',  'bg-amber-500'],
  Migrating:  ['bg-amber-50 text-amber-800',  'bg-amber-500'],
  Errored:    ['bg-red-50 text-red-700',      'bg-red-500'],
  Broken:     ['bg-red-50 text-red-700',      'bg-red-500'],
  Archived:   ['bg-gray-100 text-gray-500',   'bg-gray-400'],
}

const tone = computed(() => tones[props.status]?.[0] || tones.Pending[0])
const dot  = computed(() => tones[props.status]?.[1] || tones.Pending[1])
</script>
