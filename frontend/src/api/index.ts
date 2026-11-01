import { http } from './http'
import type {
  ActionDef, Artifact, CaseDetail, ElementNode, Execution, Locator, LocatorGroup,
  LocatorTypeDict, Project, ScaffoldResult, ScanCandidate, ScanImportResult,
  ScanResult, Suite, TestStep, VerifyResponse,
} from './types'

// ── 项目 ─────────────────────────────────────────────
export const listProjects = (): Promise<{ items: Project[]; total: number }> =>
  http.get('/projects')

export const listTargets = (projectId?: number): Promise<{ items: any[]; total: number }> =>
  http.get('/execution-targets', { params: { project_id: projectId } })

// ── 引擎 / 动作 / 字典 ────────────────────────────────
export const listEngines = (): Promise<{ items: any[]; total: number }> => http.get('/engines')
export const engineCapabilities = (key: string): Promise<any> =>
  http.get(`/engines/${key}/capabilities`)
export const listActions = (engineKey?: string): Promise<{ items: any[]; total: number }> =>
  http.get('/actions', { params: { engine_key: engineKey } })
export const locatorTypes = (): Promise<LocatorTypeDict> => http.get('/locator-types')

// ── 元素 ─────────────────────────────────────────────
export const listElements = (
  projectId: number,
  params: { parent_id?: number; keyword?: string } = {},
): Promise<{ mode: string; items: ElementNode[]; total: number }> =>
  http.get(`/projects/${projectId}/elements`, { params })

export const createElement = (projectId: number, body: {
  parent_id: number; element_name: string; node_type: 'ELEMENT' | 'FOLDER';
  description?: string; memo?: string
}): Promise<ElementNode> => http.post(`/projects/${projectId}/elements`, body)

export const getElement = (id: number): Promise<ElementNode> => http.get(`/elements/${id}`)

export const updateElement = (id: number, body: Partial<{
  element_name: string; description: string; memo: string; node_type: 'ELEMENT' | 'FOLDER'
}>): Promise<ElementNode> => http.patch(`/elements/${id}`, body)

export const deleteElement = (id: number, force = false): Promise<any> =>
  http.delete(`/elements/${id}`, { params: { force } })

export const moveElement = (id: number, body: { parent_id: number; index?: number }): Promise<any> =>
  http.post(`/elements/${id}/move`, body)

export const reorderChildren = (id: number, orderedIds: number[]): Promise<any> =>
  http.put(`/elements/${id}/children-order`, { ordered_ids: orderedIds })

export const elementReferences = (id: number): Promise<any> => http.get(`/elements/${id}/references`)

export const elementStats = (projectId: number): Promise<any> =>
  http.get(`/projects/${projectId}/element-stats`)

// ── 定位符 ───────────────────────────────────────────
export const listLocators = (elementId: number): Promise<{
  element_id: number; groups: LocatorGroup[]; coverage: Record<string, number>
}> => http.get(`/elements/${elementId}/locators`)

export const createLocator = (elementId: number, body: {
  platform: string; engine_key: string; locator_type: string;
  locator_value: string; priority?: number
}): Promise<Locator> => http.post(`/elements/${elementId}/locators`, body)

export const updateLocator = (locatorId: number, body: Partial<{
  locator_value: string; enabled: boolean; remark: string
}>): Promise<Locator> => http.patch(`/element-locators/${locatorId}`, body)

export const deleteLocator = (locatorId: number): Promise<void> =>
  http.delete(`/element-locators/${locatorId}`)

export const reorderLocators = (
  elementId: number, platform: string, engineKey: string, orderedIds: number[],
): Promise<any> => http.put(`/elements/${elementId}/locators/order`, {
  platform, engine_key: engineKey, ordered_ids: orderedIds,
})

export const verifyLocators = (elementId: number, body: {
  platform: string; engine_key: string; target_id?: number | null; url?: string | null;
  include_saved: boolean; drafts?: { locator_type: string; locator_value: string }[]
}): Promise<VerifyResponse> => http.post(`/elements/${elementId}/locators:verify`, body)

export const setPrimaryLocator = (locatorId: number): Promise<Locator> =>
  http.post(`/element-locators/${locatorId}:set-primary`)

// ── 用例 / 执行 ──────────────────────────────────────
export const listCases = (projectId: number): Promise<{ items: any[]; total: number }> =>
  http.get(`/projects/${projectId}/cases`)
export const getCase = (caseId: number): Promise<CaseDetail> => http.get(`/cases/${caseId}`)
export const createCase = (projectId: number, body: { title: string; description?: string }):
  Promise<any> => http.post(`/projects/${projectId}/cases`, body)
export const updateCase = (caseId: number, body: Partial<{ title: string; description: string }>):
  Promise<any> => http.patch(`/cases/${caseId}`, body)
export const deleteCase = (caseId: number): Promise<void> => http.delete(`/cases/${caseId}`)

export const listSteps = (caseId: number): Promise<{ items: TestStep[]; total: number }> =>
  http.get(`/cases/${caseId}/steps`)
export const createStep = (caseId: number, body: {
  seq?: number | null; action_key: string; element_id?: number | null;
  params?: Record<string, unknown>; output_var?: string | null; timeout_ms?: number | null;
  on_failure?: 'ABORT' | 'CONTINUE' | 'RETRY'; retry_times?: number;
  enabled?: boolean; remark?: string | null
}): Promise<TestStep> => http.post(`/cases/${caseId}/steps`, body)
export const updateStep = (caseId: number, stepId: number, body: Partial<{
  seq: number; action_key: string; element_id: number | null;
  params: Record<string, unknown>; output_var: string | null; timeout_ms: number | null;
  on_failure: 'ABORT' | 'CONTINUE' | 'RETRY'; retry_times: number;
  enabled: boolean; remark: string | null
}>): Promise<TestStep> => http.patch(`/cases/${caseId}/steps/${stepId}`, body)
export const deleteStep = (caseId: number, stepId: number): Promise<void> =>
  http.delete(`/cases/${caseId}/steps/${stepId}`)
export const reorderSteps = (caseId: number, orderedIds: number[]): Promise<any> =>
  http.put(`/cases/${caseId}/steps/order`, { ordered_ids: orderedIds })

/** 动作字典：StepEditor 按 params_schema 自动生成表单（Q-09） */
export const listActionDefs = (): Promise<{ items: ActionDef[]; total: number }> =>
  http.get('/actions')

export const listExecutions = (
  projectId?: number, suiteId?: number | null,
): Promise<{ items: Execution[]; total: number }> =>
  http.get('/executions', { params: { project_id: projectId, suite_id: suiteId || undefined } })
export const runExecution = (body: {
  project_id?: number; case_ids?: number[]; suite_id?: number; target_id?: number | null
}): Promise<{ id: number; status: string; queued_at: string | null }> =>
  http.post('/executions', body)
export const getExecution = (id: number): Promise<Execution> => http.get(`/executions/${id}`)
export const cancelExecution = (id: number): Promise<{ id: number; status: string }> =>
  http.post(`/executions/${id}:cancel`)
export const executionReportUrl = (id: number, format: 'html' | 'json' = 'html'): string =>
  `/api/v1/executions/${id}/report?format=${format}`
export const listArtifacts = (executionId: number): Promise<{ items: Artifact[]; total: number }> =>
  http.get(`/executions/${executionId}/artifacts`)

// ── 用例集（M3.3）────────────────────────────────────
export const listSuites = (projectId: number): Promise<{ items: Suite[]; total: number }> =>
  http.get(`/projects/${projectId}/suites`)
export const createSuite = (projectId: number, body: {
  name: string; description?: string; schedule_cron?: string | null; schedule_enabled?: boolean
}): Promise<Suite> => http.post(`/projects/${projectId}/suites`, body)
export const getSuite = (suiteId: number): Promise<Suite> => http.get(`/suites/${suiteId}`)
export const updateSuite = (suiteId: number, body: Partial<{
  name: string; description: string; schedule_cron: string | null; schedule_enabled: boolean
}>): Promise<Suite> => http.patch(`/suites/${suiteId}`, body)
export const deleteSuite = (suiteId: number): Promise<void> => http.delete(`/suites/${suiteId}`)
export const addSuiteCases = (suiteId: number, caseIds: number[]):
  Promise<{ added: number[]; skipped: number[]; invalid: number[] }> =>
  http.post(`/suites/${suiteId}/cases`, { case_ids: caseIds })
export const removeSuiteCase = (suiteId: number, caseId: number): Promise<void> =>
  http.delete(`/suites/${suiteId}/cases/${caseId}`)
export const toggleSuiteCase = (suiteId: number, caseId: number, enabled: boolean):
  Promise<{ suite_id: number; case_id: number; enabled: boolean }> =>
  http.patch(`/suites/${suiteId}/cases/${caseId}`, { enabled })
export const reorderSuiteCases = (suiteId: number, orderedCaseIds: number[]): Promise<any> =>
  http.put(`/suites/${suiteId}/cases/order`, { ordered_case_ids: orderedCaseIds })
export const runSuite = (suiteId: number):
  Promise<{ id: number; status: string; suite_name: string; case_count: number }> =>
  http.post(`/suites/${suiteId}:run`)

// ── 一键接入（M3.4）──────────────────────────────────
export const scaffold = (body: {
  project: { name: string; code: string; platform: string; engine_key: string; description?: string }
  url: string
  target?: { name?: string; options?: Record<string, unknown> }
  elements: {
    key: string; name: string; description?: string
    locators: { locator_type: string; locator_value: string }[]
  }[]
  actions: {
    action_key: string; element_key?: string; params?: Record<string, unknown>
    output_var?: string | null; timeout_ms?: number | null
    on_failure?: 'ABORT' | 'CONTINUE' | 'RETRY'; retry_times?: number
  }[]
  case: { title: string; description?: string; strategy?: 'reuse' | 'recreate' }
  suite: { name: string; description?: string }
  run?: boolean
}): Promise<ScaffoldResult> => http.post('/scaffold', body)

// ── 页面扫描（M3.5）──────────────────────────────────
export const scanPage = (projectId: number, body: {
  url?: string | null; max_elements?: number; include?: string[]
}): Promise<ScanResult> => http.post(`/projects/${projectId}/element-scan`, body)

export const importScanCandidates = (projectId: number, body: {
  candidates: { name: string; locators: { locator_type: string; locator_value: string }[] }[]
}): Promise<ScanImportResult> => http.post(`/projects/${projectId}/element-scan/import`, body)
