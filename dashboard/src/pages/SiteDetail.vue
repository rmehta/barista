<template>
  <div class="p-6 space-y-4" v-if="site.data">
    <header class="flex items-center justify-between">
      <div class="space-y-1">
        <RouterLink to="/sites" class="text-xs text-gray-500 hover:underline">← Sites</RouterLink>
        <h1 class="text-xl font-semibold flex items-center gap-2">
          {{ site.data.site_name }}
          <StatusBadge :status="site.data.status" />
          <span v-if="site.data.is_control_plane" class="text-xs text-gray-500">(control plane)</span>
        </h1>
      </div>
      <div class="flex gap-2">
        <Button @click="call('backup',  { with_files: 1 })">Backup</Button>
        <Button @click="call('migrate')">Migrate</Button>
        <Button v-if="!site.data.is_control_plane" theme="red" @click="archive()">Archive</Button>
      </div>
    </header>

    <section class="grid grid-cols-3 gap-4">
      <Card label="Bench" :value="site.data.bench" />
      <Card label="DB Name" :value="site.data.db_name || '—'" :mono="true" />
      <Card label="Created" :value="site.data.created_on || '—'" />
    </section>

    <section>
      <h2 class="text-sm font-medium mb-2">Recent backups</h2>
      <table class="w-full text-sm bg-white border border-gray-200 rounded-lg">
        <thead class="text-left text-xs uppercase text-gray-500 bg-gray-50">
          <tr>
            <th class="px-4 py-2 font-medium">When</th>
            <th class="px-4 py-2 font-medium">Type</th>
            <th class="px-4 py-2 font-medium">Status</th>
            <th class="px-4 py-2 font-medium">Size</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="b in backups.data" :key="b.name" class="border-t border-gray-100">
            <td class="px-4 py-2 text-gray-600">{{ b.started_at }}</td>
            <td class="px-4 py-2">{{ b.type }}</td>
            <td class="px-4 py-2"><StatusBadge :status="b.status" /></td>
            <td class="px-4 py-2 text-gray-600">{{ b.size_mb ? `${b.size_mb} MB` : '—' }}</td>
          </tr>
          <tr v-if="!backups.data?.length">
            <td colspan="4" class="px-4 py-4 text-center text-sm text-gray-500">No backups yet.</td>
          </tr>
        </tbody>
      </table>
    </section>

    <ActionConfirm
      v-model="confirmingArchive"
      title="Archive site"
      :message="`This will drop site '${site.data?.site_name}' on the bench. The Site row stays for the audit trail. Continue?`"
      confirm-label="Archive"
      variant="solid"
      @confirm="doArchive"
    />
  </div>
</template>

<script setup>
import { computed, h, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { Button, toast, createListResource } from 'frappe-ui'
import { getSite, siteAction } from '../lib/api'
import StatusBadge from '../components/StatusBadge.vue'
import ActionConfirm from '../components/ActionConfirm.vue'

const props = defineProps({ name: { type: String, required: true } })

const site = getSite(props.name)
const backups = createListResource({
  doctype: 'Site Backup',
  fields: ['name', 'type', 'status', 'size_mb', 'started_at'],
  filters: { site: props.name },
  orderBy: 'started_at desc',
  pageLength: 20,
  auto: true,
})
const confirmingArchive = ref(false)

function call(method, extra = {}) {
  siteAction(method).submit({ site: props.name, ...extra }, {
    onSuccess: () => { toast.success(`${method} queued`); site.reload(); backups.reload() },
    onError: (e) => toast.error(e.message || String(e)),
  })
}

function archive() { confirmingArchive.value = true }
function doArchive() {
  confirmingArchive.value = false
  call('archive')
}

// tiny inline Card
const Card = {
  props: ['label', 'value', 'mono'],
  setup: (props) => () =>
    h('div', { class: 'bg-white border border-gray-200 rounded-lg p-4' }, [
      h('div', { class: 'text-xs text-gray-500' }, props.label),
      h('div', { class: props.mono ? 'font-mono text-xs' : 'font-medium' }, props.value),
    ]),
}
</script>
