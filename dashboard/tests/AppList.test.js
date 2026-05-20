import { describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

import * as api from '../src/lib/api'
import AppList from '../src/pages/AppList.vue'

function stubApps(data) {
  vi.spyOn(api, 'listApps').mockReturnValue({
    data,
    loading: false,
    reload: vi.fn(),
  })
}

describe('AppList', () => {
  it('shows empty state when no apps match filter', async () => {
    stubApps([
      { name: 'erpnext', app_name: 'erpnext', title: 'ERPNext',
        repository_url: 'https://github.com/frappe/erpnext',
        default_branch: 'version-15', is_first_party: true },
    ])
    const w = mount(AppList)
    await flushPromises()
    await w.find('input').setValue('nonexistent-search')
    expect(w.text()).toContain('No apps match')
  })

  it('renders one card per app with the right badges', async () => {
    stubApps([
      { name: 'erpnext', app_name: 'erpnext', title: 'ERPNext',
        repository_url: 'https://github.com/frappe/erpnext',
        default_branch: 'version-15', is_first_party: true },
      { name: 'myapp', app_name: 'myapp', title: 'My App',
        repository_url: 'https://github.com/me/myapp',
        default_branch: 'main', is_first_party: false, is_private: 1 },
    ])
    const w = mount(AppList)
    await flushPromises()

    const items = w.findAll('li')
    expect(items).toHaveLength(2)

    expect(items[0].text()).toContain('ERPNext')
    expect(items[0].text()).toContain('official')

    expect(items[1].text()).toContain('My App')
    expect(items[1].text()).toContain('custom')
    expect(items[1].text()).toContain('private')
  })

  it('filters by query against name, title, and url', async () => {
    stubApps([
      { name: 'erpnext', app_name: 'erpnext', title: 'ERPNext',
        repository_url: 'https://github.com/frappe/erpnext',
        default_branch: 'version-15', is_first_party: true },
      { name: 'crm', app_name: 'crm', title: 'Frappe CRM',
        repository_url: 'https://github.com/frappe/crm',
        default_branch: 'main', is_first_party: true },
    ])
    const w = mount(AppList)
    await flushPromises()
    await w.find('input').setValue('crm')
    const items = w.findAll('li')
    expect(items).toHaveLength(1)
    expect(items[0].text()).toContain('Frappe CRM')
  })

  it('has a + Add Custom App button', () => {
    stubApps([])
    const w = mount(AppList)
    expect(w.text()).toContain('+ Add Custom App')
  })
})
