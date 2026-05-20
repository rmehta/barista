import { describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

import * as api from '../src/lib/api'
import NewSiteDialog from '../src/components/NewSiteDialog.vue'

function stubAll({ benches = [], apps = [] } = {}) {
  vi.spyOn(api, 'listBenches').mockReturnValue({ data: benches, loading: false, reload: vi.fn() })
  vi.spyOn(api, 'listApps').mockReturnValue({ data: apps, loading: false, reload: vi.fn() })

  const submit = vi.fn()
  vi.spyOn(api, 'siteAction').mockReturnValue({
    data: null, loading: false, error: null, submit, onSuccess: null,
  })
  return { submit }
}

describe('NewSiteDialog', () => {
  const benches = [
    { name: 'default', bench_name: 'default', status: 'Running' },
    { name: 'erp',     bench_name: 'erp',     status: 'Stopped' },
  ]

  const apps = [
    { app_name: 'frappe',  title: 'Frappe',  is_first_party: true },
    { app_name: 'erpnext', title: 'ERPNext', is_first_party: true },
    { app_name: 'hrms',    title: 'Frappe HR', is_first_party: true },
    { app_name: 'myapp',   title: 'My App',  is_first_party: false },
  ]

  it('lists installable apps (excluding frappe)', async () => {
    stubAll({ benches, apps })
    const w = mount(NewSiteDialog, { props: { modelValue: true } })
    await flushPromises()
    const section = w.find('[data-test="apps-section"]')
    expect(section.exists()).toBe(true)
    expect(section.text()).toContain('ERPNext')
    expect(section.text()).toContain('Frappe HR')
    expect(section.text()).toContain('My App')
    // frappe itself is excluded from the picker
    expect(section.findAll('label').filter((l) => l.text() === 'Frappe')).toHaveLength(0)
  })

  it('flags custom apps in the picker', async () => {
    stubAll({ benches, apps })
    const w = mount(NewSiteDialog, { props: { modelValue: true } })
    await flushPromises()
    const section = w.find('[data-test="apps-section"]')
    expect(section.text()).toContain('(custom)')
  })

  it('only offers running benches in the dropdown', async () => {
    stubAll({ benches, apps })
    const w = mount(NewSiteDialog, { props: { modelValue: true } })
    await flushPromises()
    // we can verify the bench dropdown was populated via the
    // component's computed by checking that the form was bound to a
    // running bench
    expect(w.vm.form.bench).toBe('default')
  })

  it('submits with the picked apps', async () => {
    const { submit } = stubAll({ benches, apps })
    const w = mount(NewSiteDialog, { props: { modelValue: true } })
    await flushPromises()

    // bench is preselected by the immediate watcher; fill the rest
    // via the exposed form ref.
    w.vm.form.site_name = 'shop.localhost'
    w.vm.form.admin_password = 'shop-admin-pw-12345'
    w.vm.form.mariadb_root_password = 'mdb-root-pw'
    w.vm.form.apps = ['erpnext', 'hrms']

    w.vm.submit()
    expect(submit).toHaveBeenCalledTimes(1)
    const arg = submit.mock.calls[0][0]
    expect(arg.site_name).toBe('shop.localhost')
    expect(arg.bench).toBe('default')
    expect(arg.apps).toEqual(['erpnext', 'hrms'])
  })

  it('blocks submit when required fields are empty', async () => {
    const { submit } = stubAll({ benches, apps })
    const w = mount(NewSiteDialog, { props: { modelValue: true } })
    await flushPromises()

    w.vm.form.site_name = ''
    w.vm.form.admin_password = 'x'
    w.vm.form.mariadb_root_password = 'y'
    w.vm.submit()
    expect(submit).not.toHaveBeenCalled()
  })
})
