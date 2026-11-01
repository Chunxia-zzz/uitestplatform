import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  elementStats, listElements, listLocators, listProjects, locatorTypes, verifyLocators,
} from '@/api'
import type {
  ElementNode, LocatorGroup, LocatorTypeDict, Project, VerifyResponse,
} from '@/api/types'
import { toastInfo } from '@/components/AppToast'

export const useElementStore = defineStore('element', () => {
  const projects = ref<Project[]>([])
  const projectId = ref<number | null>(null)
  const tree = ref<ElementNode[]>([])
  const expanded = ref<Set<number>>(new Set())
  const selectedId = ref<number | null>(null)
  const detail = ref<ElementNode | null>(null)
  const groups = ref<LocatorGroup[]>([])
  const coverage = ref<Record<string, number>>({ WEB: 0, ANDROID: 0, IOS: 0 })
  const dict = ref<LocatorTypeDict | null>(null)
  const stats = ref<any>(null)
  const verifyResult = ref<VerifyResponse | null>(null)
  const loading = ref({ tree: false, locators: false, verify: false })

  const currentProject = computed(() =>
    projects.value.find((p) => p.id === projectId.value) ?? null)

  const selectedNode = computed(() => {
    if (!selectedId.value) return null
    const walk = (nodes: ElementNode[]): ElementNode | null => {
      for (const node of nodes) {
        if (node.id === selectedId.value) return node
        const hit = walk(node.children || [])
        if (hit) return hit
      }
      return null
    }
    return walk(tree.value)
  })

  async function init() {
    const [projectResp, dictResp] = await Promise.all([listProjects(), locatorTypes()])
    projects.value = projectResp.items
    dict.value = dictResp
    if (!projectId.value && projects.value.length) {
      projectId.value = projects.value[0].id
    }
    if (projectId.value) await loadTree()
  }

  async function loadTree() {
    if (!projectId.value) return
    loading.value.tree = true
    try {
      const resp = await listElements(projectId.value)
      tree.value = resp.items
      stats.value = await elementStats(projectId.value)

      // 首次进入：展开目录并选中第一个元素 —— 否则新用户看到的是一棵收起的树 + 空白右栏
      if (!selectedId.value) {
        expandAll()
        const first = findFirstElement(tree.value)
        if (first) await selectNode(first.id)
      } else {
        await refreshSelected()
      }
    } finally {
      loading.value.tree = false
    }
  }

  function findFirstElement(nodes: ElementNode[]): ElementNode | null {
    for (const node of nodes) {
      if (node.node_type === 'ELEMENT') return node
      const hit = findFirstElement(node.children || [])
      if (hit) return hit
    }
    return null
  }

  async function refreshSelected() {
    if (!selectedId.value) return
    await Promise.all([loadLocators(selectedId.value), refreshDetail()])
  }

  async function refreshDetail() {
    // 详情直接取树里的节点 + locators 的 coverage，避免为"选中项"多发一次请求
    detail.value = selectedNode.value
  }

  async function selectNode(id: number) {
    selectedId.value = id
    detail.value = selectedNode.value
    verifyResult.value = null
    await loadLocators(id)
  }

  async function loadLocators(elementId: number) {
    loading.value.locators = true
    try {
      const resp = await listLocators(elementId)
      groups.value = resp.groups
      coverage.value = { WEB: 0, ANDROID: 0, IOS: 0, ...resp.coverage }
    } finally {
      loading.value.locators = false
    }
  }

  async function verify(elementId: number, platform: string, engineKey: string,
                        drafts: { locator_type: string; locator_value: string }[] = []) {
    if (!currentProject.value) return
    loading.value.verify = true
    try {
      const resp = await verifyLocators(elementId, {
        platform, engine_key: engineKey,
        target_id: currentProject.value.target_id,
        include_saved: true,
        drafts,
      })
      verifyResult.value = resp
      const { valid, multiple, none, error } = resp.summary
      toastInfo(`验证完成：有效 ${valid} / 多条 ${multiple} / 未命中 ${none} / 异常 ${error}`)
      await loadLocators(elementId)
      return resp
    } finally {
      loading.value.verify = false
    }
  }

  function toggle(id: number) {
    const next = new Set(expanded.value)
    next.has(id) ? next.delete(id) : next.add(id)
    expanded.value = next
  }

  function expandAll(nodes: ElementNode[] = tree.value) {
    const next = new Set(expanded.value)
    const walk = (items: ElementNode[]) => {
      for (const item of items) {
        if (item.node_type === 'FOLDER') next.add(item.id)
        walk(item.children || [])
      }
    }
    walk(nodes)
    expanded.value = next
  }

  return {
    projects, projectId, tree, expanded, selectedId, detail, groups, coverage, dict, stats,
    verifyResult, loading, currentProject, selectedNode,
    init, loadTree, selectNode, loadLocators, verify, toggle, expandAll, refreshSelected,
  }
})
