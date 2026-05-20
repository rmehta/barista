// Small helpers around frappe-ui's resource API. Components don't
// import frappe-ui's primitives directly; they go through these so
// the shape can evolve in one place.

import { createListResource, createResource } from 'frappe-ui'

export function listBenches() {
  return createListResource({
    doctype: 'Bench Host',
    fields: ['name', 'bench_name', 'spec', 'status', 'http_port', 'container_id'],
    orderBy: 'bench_name asc',
    pageLength: 50,
    auto: true,
  })
}

export function listSites() {
  return createListResource({
    doctype: 'Site',
    fields: ['name', 'site_name', 'bench', 'status', 'is_control_plane', 'backup_schedule'],
    orderBy: 'site_name asc',
    pageLength: 100,
    auto: true,
  })
}

export function benchAction(method) {
  return createResource({
    url: `barista.api.bench.${method}`,
    method: 'POST',
  })
}

export function siteAction(method) {
  return createResource({
    url: `barista.api.site.${method}`,
    method: 'POST',
  })
}

export function getBench(name) {
  return createResource({
    url: 'frappe.client.get',
    auto: true,
    params: { doctype: 'Bench Host', name },
  })
}

export function getSite(name) {
  return createResource({
    url: 'frappe.client.get',
    auto: true,
    params: { doctype: 'Site', name },
  })
}

export function listSpecs() {
  return createListResource({
    doctype: 'Bench Spec',
    fields: ['name', 'spec_name', 'python_version', 'node_version', 'frappe_branch'],
    pageLength: 100,
    auto: true,
  })
}
