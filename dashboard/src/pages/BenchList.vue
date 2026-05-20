<template>
  <div class="p-6 space-y-4">
    <header class="flex items-center justify-between">
      <h1 class="text-xl font-semibold">Benches</h1>
      <Button variant="solid" @click="showNew = true">+ New Bench</Button>
    </header>

    <div v-if="benches.loading" class="text-sm text-gray-500">Loading…</div>

    <div v-else-if="!benches.data?.length"
         class="rounded-lg border border-dashed border-gray-300 p-8 text-center text-sm text-gray-500">
      No benches yet. Click <em>+ New Bench</em> to create one.
    </div>

    <table v-else class="w-full text-sm bg-white border border-gray-200 rounded-lg overflow-hidden">
      <thead class="text-left text-xs uppercase text-gray-500 bg-gray-50">
        <tr>
          <th class="px-4 py-2 font-medium">Name</th>
          <th class="px-4 py-2 font-medium">Spec</th>
          <th class="px-4 py-2 font-medium">Status</th>
          <th class="px-4 py-2 font-medium">Port</th>
          <th class="px-4 py-2 font-medium text-right">Actions</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="b in benches.data" :key="b.name" class="border-t border-gray-100 hover:bg-gray-50">
          <td class="px-4 py-2">
            <RouterLink :to="`/benches/${b.name}`" class="text-blue-600 hover:underline">
              {{ b.bench_name }}
            </RouterLink>
          </td>
          <td class="px-4 py-2 text-gray-600">{{ b.spec }}</td>
          <td class="px-4 py-2"><StatusBadge :status="b.status" /></td>
          <td class="px-4 py-2 text-gray-600">{{ b.http_port || '—' }}</td>
          <td class="px-4 py-2 text-right">
            <Dropdown :options="actionsFor(b)">
              <Button variant="ghost" icon="more-horizontal" />
            </Dropdown>
          </td>
        </tr>
      </tbody>
    </table>

    <NewBenchDialog v-model="showNew" @created="benches.reload()" />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { RouterLink } from 'vue-router'
import { Button, Dropdown, toast } from 'frappe-ui'
import { listBenches, benchAction } from '../lib/api'
import StatusBadge from '../components/StatusBadge.vue'
import NewBenchDialog from '../components/NewBenchDialog.vue'

const benches = listBenches()
const showNew = ref(false)

function call(method, bench) {
  benchAction(method).submit({ bench: bench.name }, {
    onSuccess: () => {
      toast.success(`${method} queued for ${bench.bench_name}`)
      benches.reload()
    },
    onError: (e) => toast.error(e.message || String(e)),
  })
}

function actionsFor(b) {
  return [
    { label: 'Start',   onClick: () => call('start', b), disabled: b.status === 'Running' },
    { label: 'Stop',    onClick: () => call('stop', b),  disabled: b.status !== 'Running' },
    { label: 'Restart', onClick: () => call('restart', b), disabled: b.status !== 'Running' },
    { divider: true },
    { label: 'Destroy', onClick: () => call('destroy', b), theme: 'red' },
  ]
}
</script>
