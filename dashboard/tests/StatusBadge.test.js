import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import StatusBadge from '../src/components/StatusBadge.vue'

describe('StatusBadge', () => {
  it('renders the status text', () => {
    const w = mount(StatusBadge, { props: { status: 'Running' } })
    expect(w.text()).toContain('Running')
  })

  it('maps Running to a green tone', () => {
    const w = mount(StatusBadge, { props: { status: 'Running' } })
    expect(w.html()).toMatch(/bg-green-50/)
    expect(w.html()).toMatch(/text-green-700/)
  })

  it('maps Errored to a red tone', () => {
    const w = mount(StatusBadge, { props: { status: 'Errored' } })
    expect(w.html()).toMatch(/bg-red-50/)
  })

  it('falls back gracefully for unknown statuses', () => {
    const w = mount(StatusBadge, { props: { status: 'WhoKnows' } })
    expect(w.text()).toContain('WhoKnows')
  })
})
