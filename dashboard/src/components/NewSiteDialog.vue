<template>
  <Dialog
    v-model="show"
    :options="{
      title: 'New Site',
      actions: [
        { label: 'Cancel', variant: 'subtle', onClick: close },
        { label: 'Create', variant: 'solid', onClick: submit, loading: creating.loading },
      ],
    }"
  >
    <template #body-content>
      <div class="space-y-3">
        <FormControl
          label="Site Name"
          v-model="form.site_name"
          placeholder="e.g. myshop.localhost"
        />
        <FormControl
          label="Bench"
          type="select"
          v-model="form.bench"
          :options="benchOptions"
        />
        <FormControl
          label="Admin Password"
          type="password"
          v-model="form.admin_password"
        />
        <FormControl
          label="MariaDB Root Password"
          type="password"
          v-model="form.mariadb_root_password"
          description="From ~/.barista/.env on the host."
        />

        <div data-test="apps-section">
          <label class="text-sm font-medium text-gray-700">Apps to install</label>
          <p class="text-xs text-gray-500 mb-2">
            Frappe is installed by default. Pick any additional apps.
          </p>
          <div v-if="apps.loading" class="text-xs text-gray-500">Loading catalog…</div>
          <div v-else class="grid grid-cols-2 gap-1 max-h-48 overflow-auto">
            <label
              v-for="app in installableApps"
              :key="app.app_name"
              class="flex items-center gap-2 text-sm px-2 py-1 rounded hover:bg-gray-50"
            >
              <input
                type="checkbox"
                :value="app.app_name"
                v-model="form.apps"
              />
              <span>{{ app.title || app.app_name }}</span>
              <span v-if="!app.is_first_party" class="text-xs text-gray-400">(custom)</span>
            </label>
          </div>
        </div>

        <ErrorMessage v-if="creating.error" :message="creating.error.message || String(creating.error)" />
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import { computed, reactive, watch } from 'vue'
import { Dialog, FormControl, ErrorMessage } from 'frappe-ui'
import { listBenches, listApps, siteAction } from '../lib/api'

const props = defineProps({ modelValue: Boolean, preselectedBench: String })
const emit  = defineEmits(['update:modelValue', 'created'])

const show = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const form = reactive({
  site_name: '',
  bench: props.preselectedBench || '',
  admin_password: '',
  mariadb_root_password: '',
  apps: [],
})

const benches = listBenches()
const apps = listApps()

const benchOptions = computed(() =>
  (benches.data || [])
    .filter((b) => b.status === 'Running')
    .map((b) => ({ label: b.bench_name, value: b.name }))
)

const installableApps = computed(() =>
  (apps.data || []).filter((a) => a.app_name !== 'frappe')
)

watch(benchOptions, (opts) => {
  if (!form.bench && opts.length) form.bench = opts[0].value
}, { immediate: true })

const creating = siteAction('create')
creating.onSuccess = () => { emit('created'); close() }

function close() {
  show.value = false
  form.site_name = ''
  form.admin_password = ''
  form.mariadb_root_password = ''
  form.apps = []
}

function submit() {
  if (!form.site_name || !form.bench || !form.admin_password || !form.mariadb_root_password) return
  creating.submit({
    bench: form.bench,
    site_name: form.site_name,
    admin_password: form.admin_password,
    mariadb_root_password: form.mariadb_root_password,
    apps: form.apps,
  })
}

defineExpose({ form, submit })
</script>
