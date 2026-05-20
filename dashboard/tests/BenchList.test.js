import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import * as frappeUI from 'frappe-ui'

import * as api from '../src/lib/api'
import BenchList from '../src/pages/BenchList.vue'

// stub out the api module so the page doesn't try to fetch.
vi.spyOn(api, 'listBenches').mockImplementation(() => ({
  data: [],
  loading: false,
  reload: vi.fn(),
}))
vi.spyOn(api, 'benchAction').mockImplementation(() => ({ submit: vi.fn() }))

describe('BenchList', () => {
  function setup(data) {
    api.listBenches.mockReturnValue({ data, loading: false, reload: vi.fn() })
    return mount(BenchList, {
      global: {
        stubs: { RouterLink: { template: '<a><slot /></a>' } },
      },
    })
  }

  it('shows the empty state when there are no benches', async () => {
    const w = setup([])
    await new Promise((r) => setTimeout(r, 0))
    expect(w.text()).toContain('No benches yet')
  })

  it('renders one row per bench', async () => {
    const w = setup([
      { name: 'default',  bench_name: 'default',  spec: 'barista-cp', status: 'Running', http_port: 18000 },
      { name: 'erp',      bench_name: 'erp',      spec: 'erpnext',    status: 'Stopped', http_port: 18001 },
    ])
    await new Promise((r) => setTimeout(r, 0))
    const rows = w.findAll('tbody tr')
    expect(rows).toHaveLength(2)
    expect(rows[0].text()).toContain('default')
    expect(rows[1].text()).toContain('erp')
  })

  it('toolbar has a New Bench button', () => {
    const w = setup([])
    expect(w.text()).toContain('+ New Bench')
  })
})
