// Vitest setup — stub frappe-ui to avoid a real Frappe backend.

import { vi } from 'vitest'

vi.mock('frappe-ui', () => {
  function makeListResource() {
    return {
      data: [],
      loading: false,
      reload: vi.fn(),
    }
  }
  function makeResource() {
    return {
      data: null,
      loading: false,
      error: null,
      submit: vi.fn(),
      reload: vi.fn(),
    }
  }
  return {
    createListResource: () => makeListResource(),
    createResource: () => makeResource(),
    setConfig: vi.fn(),
    frappeRequest: vi.fn(),
    resourcesPlugin: { install: vi.fn() },
    FrappeUI: { install: vi.fn() },
    // simple component stubs
    Button: { template: '<button><slot /></button>', props: ['variant', 'theme', 'icon'] },
    Dialog: {
      template: `<div v-if="modelValue" data-test="dialog">
                   <div data-test="dialog-title">{{ options?.title }}</div>
                   <slot name="body-content" />
                 </div>`,
      props: ['modelValue', 'options'],
    },
    Dropdown: { template: '<div><slot /></div>', props: ['options'] },
    FormControl: {
      template: `<div data-test="form-control">
                   <label v-if="label" data-test="label">{{ label }}</label>
                   <input
                     :type="type === 'checkbox' ? 'checkbox' : (type || 'text')"
                     :placeholder="placeholder"
                     :checked="type === 'checkbox' ? !!modelValue : undefined"
                     :value="type === 'checkbox' ? undefined : modelValue"
                     @input="onInput($event)"
                     @change="onInput($event)"
                   />
                   <small v-if="description" data-test="description">{{ description }}</small>
                 </div>`,
      props: ['label', 'modelValue', 'placeholder', 'type', 'description', 'options'],
      emits: ['update:modelValue'],
      methods: {
        onInput(e) {
          const v = this.type === 'checkbox' ? e.target.checked : e.target.value
          this.$emit('update:modelValue', v)
        },
      },
    },
    ErrorMessage: { template: '<div data-test="error">{{ message }}</div>', props: ['message'] },
    Badge: {
      template: '<span data-test="badge" :data-theme="theme"><slot /></span>',
      props: ['theme', 'variant'],
    },
    toast: { success: vi.fn(), error: vi.fn() },
  }
})
