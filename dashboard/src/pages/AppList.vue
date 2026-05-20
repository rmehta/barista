<template>
  <div class="p-6 space-y-4">
    <header class="flex items-center justify-between">
      <div>
        <h1 class="text-xl font-semibold">Apps</h1>
        <p class="text-sm text-gray-500">
          Sources you can install on sites. First-party Frappe apps are
          seeded automatically; add your own via Git URL.
        </p>
      </div>
      <Button variant="solid" @click="showAdd = true">+ Add Custom App</Button>
    </header>

    <FormControl
      v-model="filter"
      placeholder="Filter by name or URL…"
      class="max-w-sm"
    />

    <div v-if="apps.loading" class="text-sm text-gray-500">Loading…</div>

    <div v-else-if="!filtered.length"
         class="rounded-lg border border-dashed border-gray-300 p-8 text-center text-sm text-gray-500">
      No apps match.
    </div>

    <ul v-else class="grid grid-cols-1 md:grid-cols-2 gap-3">
      <li
        v-for="app in filtered"
        :key="app.name"
        class="bg-white border border-gray-200 rounded-lg p-4 flex items-start gap-3"
      >
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2">
            <div class="font-medium truncate">{{ app.title || app.app_name }}</div>
            <Badge v-if="app.is_first_party" theme="green" variant="subtle">official</Badge>
            <Badge v-else theme="gray" variant="subtle">custom</Badge>
            <Badge v-if="app.is_private" theme="amber" variant="subtle">private</Badge>
          </div>
          <div class="text-xs text-gray-500 font-mono truncate">{{ app.repository_url }}</div>
          <div v-if="app.description" class="text-sm text-gray-600 mt-1">{{ app.description }}</div>
          <div class="text-xs text-gray-500 mt-1">branch: {{ app.default_branch }}</div>
        </div>
      </li>
    </ul>

    <AddCustomAppDialog v-model="showAdd" @created="apps.reload()" />
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { Button, Badge, FormControl } from 'frappe-ui'
import { listApps } from '../lib/api'
import AddCustomAppDialog from '../components/AddCustomAppDialog.vue'

const apps = listApps()
const showAdd = ref(false)
const filter = ref('')

const filtered = computed(() => {
  const rows = apps.data || []
  const q = filter.value.trim().toLowerCase()
  if (!q) return rows
  return rows.filter((r) =>
    (r.app_name || '').toLowerCase().includes(q) ||
    (r.title || '').toLowerCase().includes(q) ||
    (r.repository_url || '').toLowerCase().includes(q)
  )
})
</script>
