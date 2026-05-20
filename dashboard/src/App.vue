<template>
  <div class="min-h-screen flex bg-gray-50 text-gray-900">
    <aside class="w-56 border-r border-gray-200 bg-white flex flex-col">
      <div class="p-4 text-lg font-semibold flex items-center gap-2">
        <span aria-hidden="true">☕</span>
        Barista
      </div>
      <nav class="flex-1 px-2 space-y-1">
        <RouterLink
          v-for="item in nav"
          :key="item.to"
          :to="item.to"
          class="block px-3 py-2 rounded-md text-sm hover:bg-gray-100"
          active-class="bg-gray-100 font-medium"
        >
          {{ item.label }}
        </RouterLink>
      </nav>
      <div class="px-4 py-3 text-xs text-gray-500 border-t border-gray-100">
        v{{ version }}
      </div>
    </aside>

    <main class="flex-1 overflow-auto">
      <RouterView />
    </main>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { RouterLink, RouterView } from 'vue-router'

const nav = [
  { to: '/benches', label: 'Benches' },
  { to: '/sites', label: 'Sites' },
]

const version = ref(window.frappe?.boot?.barista?.version || '0.0.1')
</script>
