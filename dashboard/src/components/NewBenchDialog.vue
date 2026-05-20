<template>
  <Dialog
    v-model="show"
    :options="{
      title: 'New Bench',
      actions: [
        { label: 'Cancel', variant: 'subtle', onClick: close },
        { label: 'Create', variant: 'solid', onClick: submit, loading: creating.loading },
      ],
    }"
  >
    <template #body-content>
      <div class="space-y-3">
        <FormControl
          label="Bench Name"
          v-model="form.bench_name"
          placeholder="e.g. myproject"
          :description="'Lowercase letters, digits, hyphens (2–30 chars).'"
        />
        <FormControl
          label="Spec"
          type="select"
          v-model="form.spec"
          :options="specOptions"
        />
        <ErrorMessage v-if="creating.error" :message="creating.error.message || String(creating.error)" />
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { Dialog, FormControl, ErrorMessage, createResource } from 'frappe-ui'
import { listSpecs } from '../lib/api'

const props = defineProps({ modelValue: Boolean })
const emit  = defineEmits(['update:modelValue', 'created'])

const show = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const form = reactive({ bench_name: '', spec: '' })
const specs = listSpecs()

const specOptions = computed(() =>
  (specs.data || []).map((s) => ({ label: s.name, value: s.name }))
)

watch(specOptions, (opts) => {
  if (!form.spec && opts.length) form.spec = opts[0].value
}, { immediate: true })

const creating = createResource({
  url: 'frappe.client.insert',
  onSuccess: (doc) => {
    emit('created', doc)
    close()
  },
})

function close() {
  show.value = false
  form.bench_name = ''
}

function submit() {
  if (!form.bench_name || !form.spec) return
  creating.submit({
    doc: {
      doctype: 'Bench Host',
      bench_name: form.bench_name,
      spec: form.spec,
      status: 'Pending',
    },
  })
}
</script>
