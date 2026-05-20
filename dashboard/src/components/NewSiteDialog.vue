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
        <ErrorMessage v-if="creating.error" :message="creating.error.message || String(creating.error)" />
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import { computed, reactive, watch } from 'vue'
import { Dialog, FormControl, ErrorMessage, createResource } from 'frappe-ui'
import { listBenches, siteAction } from '../lib/api'

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
})

const benches = listBenches()
const benchOptions = computed(() =>
  (benches.data || [])
    .filter((b) => b.status === 'Running')
    .map((b) => ({ label: b.bench_name, value: b.name }))
)

watch(benchOptions, (opts) => {
  if (!form.bench && opts.length) form.bench = opts[0].value
})

const creating = siteAction('create')
creating.onSuccess = () => {
  emit('created')
  close()
}

function close() {
  show.value = false
  form.site_name = ''
  form.admin_password = ''
  form.mariadb_root_password = ''
}

function submit() {
  if (!form.site_name || !form.bench || !form.admin_password || !form.mariadb_root_password) return
  creating.submit({
    bench: form.bench,
    site_name: form.site_name,
    admin_password: form.admin_password,
    mariadb_root_password: form.mariadb_root_password,
  })
}
</script>
