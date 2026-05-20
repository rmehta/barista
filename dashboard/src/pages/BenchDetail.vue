<template>
  <div class="p-6 space-y-4" v-if="bench.data">
    <header class="flex items-center justify-between">
      <div class="space-y-1">
        <RouterLink to="/benches" class="text-xs text-gray-500 hover:underline">← Benches</RouterLink>
        <h1 class="text-xl font-semibold flex items-center gap-2">
          {{ bench.data.bench_name }}
          <StatusBadge :status="bench.data.status" />
        </h1>
      </div>
      <div class="flex gap-2">
        <Button @click="call('restart')" :disabled="bench.data.status !== 'Running'">Restart</Button>
        <Button @click="call('stop')"    :disabled="bench.data.status !== 'Running'">Stop</Button>
        <Button @click="call('start')"   :disabled="bench.data.status === 'Running'">Start</Button>
      </div>
    </header>

    <section class="grid grid-cols-3 gap-4">
      <div class="bg-white border border-gray-200 rounded-lg p-4">
        <div class="text-xs text-gray-500">Spec</div>
        <div class="font-medium">{{ bench.data.spec }}</div>
      </div>
      <div class="bg-white border border-gray-200 rounded-lg p-4">
        <div class="text-xs text-gray-500">HTTP port</div>
        <div class="font-medium">{{ bench.data.http_port || '—' }}</div>
      </div>
      <div class="bg-white border border-gray-200 rounded-lg p-4">
        <div class="text-xs text-gray-500">Container</div>
        <div class="font-mono text-xs">{{ bench.data.container_id || '—' }}</div>
      </div>
    </section>

    <section>
      <header class="flex items-center justify-between mb-2">
        <h2 class="text-sm font-medium">Sites on this bench</h2>
        <Button variant="solid" @click="showNewSite = true">+ New Site</Button>
      </header>
      <table class="w-full text-sm bg-white border border-gray-200 rounded-lg">
        <thead class="text-left text-xs uppercase text-gray-500 bg-gray-50">
          <tr>
            <th class="px-4 py-2 font-medium">Site</th>
            <th class="px-4 py-2 font-medium">Status</th>
            <th class="px-4 py-2 font-medium">Backups</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in sitesOnBench" :key="s.name" class="border-t border-gray-100 hover:bg-gray-50">
            <td class="px-4 py-2">
              <RouterLink :to="`/sites/${s.name}`" class="text-blue-600 hover:underline">{{ s.site_name }}</RouterLink>
            </td>
            <td class="px-4 py-2"><StatusBadge :status="s.status" /></td>
            <td class="px-4 py-2 text-gray-600">{{ s.backup_schedule || 'None' }}</td>
          </tr>
          <tr v-if="!sitesOnBench.length">
            <td colspan="3" class="px-4 py-4 text-center text-sm text-gray-500">
              No sites yet on this bench.
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <NewSiteDialog v-model="showNewSite" :preselected-bench="bench.data.name" @created="sites.reload()" />
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { Button, toast } from 'frappe-ui'
import { getBench, listSites, benchAction } from '../lib/api'
import StatusBadge from '../components/StatusBadge.vue'
import NewSiteDialog from '../components/NewSiteDialog.vue'

const props = defineProps({ name: { type: String, required: true } })

const bench = getBench(props.name)
const sites = listSites()
const showNewSite = ref(false)

const sitesOnBench = computed(
  () => (sites.data || []).filter((s) => s.bench === props.name)
)

function call(method) {
  benchAction(method).submit({ bench: props.name }, {
    onSuccess: () => { toast.success(`${method} queued`); bench.reload() },
    onError: (e) => toast.error(e.message || String(e)),
  })
}
</script>
