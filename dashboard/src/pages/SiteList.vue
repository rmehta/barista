<template>
  <div class="p-6 space-y-4">
    <header class="flex items-center justify-between">
      <h1 class="text-xl font-semibold">Sites</h1>
      <Button variant="solid" @click="showNew = true">+ New Site</Button>
    </header>

    <div v-if="sites.loading" class="text-sm text-gray-500">Loading…</div>

    <div v-else-if="!sites.data?.length"
         class="rounded-lg border border-dashed border-gray-300 p-8 text-center text-sm text-gray-500">
      No sites yet.
    </div>

    <table v-else class="w-full text-sm bg-white border border-gray-200 rounded-lg overflow-hidden">
      <thead class="text-left text-xs uppercase text-gray-500 bg-gray-50">
        <tr>
          <th class="px-4 py-2 font-medium">Site</th>
          <th class="px-4 py-2 font-medium">Bench</th>
          <th class="px-4 py-2 font-medium">Status</th>
          <th class="px-4 py-2 font-medium">Backups</th>
          <th class="px-4 py-2 font-medium text-right">Actions</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="s in sites.data" :key="s.name" class="border-t border-gray-100 hover:bg-gray-50">
          <td class="px-4 py-2">
            <RouterLink :to="`/sites/${s.name}`" class="text-blue-600 hover:underline">
              {{ s.site_name }}
              <span v-if="s.is_control_plane" class="ml-1 text-xs text-gray-500">(control plane)</span>
            </RouterLink>
          </td>
          <td class="px-4 py-2 text-gray-600">{{ s.bench }}</td>
          <td class="px-4 py-2"><StatusBadge :status="s.status" /></td>
          <td class="px-4 py-2 text-gray-600">{{ s.backup_schedule || 'None' }}</td>
          <td class="px-4 py-2 text-right">
            <Dropdown :options="actionsFor(s)">
              <Button variant="ghost" icon="more-horizontal" />
            </Dropdown>
          </td>
        </tr>
      </tbody>
    </table>

    <NewSiteDialog v-model="showNew" @created="sites.reload()" />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { RouterLink } from 'vue-router'
import { Button, Dropdown, toast } from 'frappe-ui'
import { listSites, siteAction } from '../lib/api'
import StatusBadge from '../components/StatusBadge.vue'
import NewSiteDialog from '../components/NewSiteDialog.vue'

const sites = listSites()
const showNew = ref(false)

function call(method, site, extra = {}) {
  siteAction(method).submit({ site: site.name, ...extra }, {
    onSuccess: () => { toast.success(`${method} queued`); sites.reload() },
    onError: (e) => toast.error(e.message || String(e)),
  })
}

function actionsFor(s) {
  const ctrl = s.is_control_plane
  return [
    { label: 'Backup',  onClick: () => call('backup', s) },
    { label: 'Migrate', onClick: () => call('migrate', s) },
    { divider: true },
    { label: 'Archive', onClick: () => call('archive', s), theme: 'red', disabled: ctrl },
  ]
}
</script>
