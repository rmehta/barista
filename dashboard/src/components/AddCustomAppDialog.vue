<template>
  <Dialog
    v-model="show"
    :options="{
      title: 'Add Custom App',
      actions: [
        { label: 'Cancel', variant: 'subtle', onClick: close },
        { label: 'Add', variant: 'solid', onClick: submit, loading: creating.loading, disabled: !canSubmit },
      ],
    }"
  >
    <template #body-content>
      <div class="space-y-3">
        <FormControl
          label="Repository URL"
          v-model="form.repository_url"
          placeholder="https://github.com/your-org/your-app"
          description="HTTPS or git@ URL. Will derive the app name from the repo unless you override it."
        />
        <FormControl
          label="Branch"
          v-model="form.default_branch"
          placeholder="main"
        />
        <FormControl
          label="App Name (optional)"
          v-model="form.app_name"
          :description="derivedHint"
          placeholder="e.g. my_app"
        />
        <FormControl
          label="Private repository?"
          type="checkbox"
          v-model="form.is_private"
          description="If checked, configure an SSH key in Barista Settings first."
        />
        <ErrorMessage v-if="error" :message="error" />
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { Dialog, FormControl, ErrorMessage } from 'frappe-ui'
import { addCustomApp } from '../lib/api'

const props = defineProps({ modelValue: Boolean })
const emit  = defineEmits(['update:modelValue', 'created'])

const show = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const form = reactive({
  repository_url: '',
  default_branch: 'main',
  app_name: '',
  is_private: false,
})

const error = ref('')

const GIT_URL_RX = /^(?:https?:\/\/[\w.\-]+(?::\d+)?\/[\w./\-]+?|git@[\w.\-]+:[\w./\-]+?)(?:\.git)?$/

const canSubmit = computed(() => GIT_URL_RX.test(form.repository_url.trim()))

const derivedHint = computed(() => {
  if (form.app_name) return ''
  if (!canSubmit.value) return 'Will derive once a valid URL is entered.'
  const tail = form.repository_url.trim().replace(/\.git$/, '').split(/[/:]/).pop()
  return `Will derive: ${tail.toLowerCase().replace(/-/g, '_')}`
})

const creating = addCustomApp()
creating.onSuccess = () => { emit('created'); close() }
creating.onError = (e) => { error.value = e?.message || String(e) }

function close() {
  show.value = false
  form.repository_url = ''
  form.app_name = ''
  form.default_branch = 'main'
  form.is_private = false
  error.value = ''
}

function submit() {
  if (!canSubmit.value) return
  error.value = ''
  creating.submit({
    repository_url: form.repository_url.trim(),
    default_branch: form.default_branch.trim() || 'main',
    app_name: form.app_name.trim() || undefined,
    is_private: form.is_private ? 1 : 0,
  })
}
</script>
