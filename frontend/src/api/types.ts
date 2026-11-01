export type Platform = 'WEB' | 'ANDROID' | 'IOS'
export type NodeType = 'ELEMENT' | 'FOLDER'

export interface Project {
  id: number
  name: string
  code: string
  platform: Platform
  engine_key: string
  target_id: number | null
  description?: string | null
}

export interface LocatorCount {
  WEB: number
  ANDROID: number
  IOS: number
}

export interface ElementNode {
  id: number
  project_id: number
  parent_id: number
  path: string
  depth: number
  element_name: string
  node_type: NodeType
  description?: string | null
  memo?: string | null
  is_shared: number
  sort: number
  locator_count: LocatorCount
  children: ElementNode[]
  path_names?: string[]
}

export interface Locator {
  id: number
  element_id: number
  platform: Platform
  engine_key: string
  locator_type: string
  locator_value: string
  priority: number
  is_primary: boolean
  enabled: boolean
  status: 'UNVERIFIED' | 'VALID' | 'INVALID'
  verified_at: string | null
  probe_detail: { matched?: number; verdict?: string; sample?: Record<string, unknown> } | null
  remark?: string | null
}

export interface LocatorGroup {
  platform: Platform
  engine_key: string
  primary_id: number | null
  items: Locator[]
}

export interface LocatorTypeSpec {
  key: string
  label: string
  example: string
  engines: string[]
  rank: number
  note: string
}

export interface LocatorTypeDict {
  platforms: Record<Platform, {
    platform: Platform
    label: string
    engines: string[]
    types: LocatorTypeSpec[]
  }>
}

export interface VerifyItem {
  locator_id: number | null
  locator_type: string
  locator_value: string
  verdict: 'VALID' | 'MULTIPLE' | 'NONE' | 'ERROR'
  matched: number
  duration_ms: number
  sample: Record<string, unknown> | null
  error?: string | null
}

export interface VerifyResponse {
  checked_at: string
  target_id: number | null
  url: string | null
  duration_ms: number
  results: VerifyItem[]
  summary: { valid: number; multiple: number; none: number; error: number }
  verdict: 'ALL_VALID' | 'HAS_PROBLEM' | 'ALL_INVALID'
}

export interface ExecutionStepResult {
  id: number
  seq: number
  step_id: number | null
  action_key: string
  element_id: number | null
  status: 'PASSED' | 'FAILED' | 'ERROR' | 'SKIPPED'
  attempt?: number
  duration_ms: number | null
  message: string | null
  used_locator_id: number | null
  fallback_index: number | null
  active_platform: string | null
  active_engine: string | null
}

export interface ExecutionCase {
  case_id: number
  title: string
  steps: ExecutionStepResult[]
}

export interface Suite {
  id: number
  project_id: number
  name: string
  description?: string | null
  schedule_cron: string | null
  schedule_enabled: boolean
  last_run_at: string | null
  case_count?: number
  cases?: SuiteCase[]
}

export interface SuiteCase {
  case_id: number
  title: string
  description?: string | null
  sort: number
  enabled: boolean
}

// ── 用例与步骤（M3.2 StepEditor）──────────────────────
export interface TestStep {
  id: number
  case_id: number
  seq: number
  action_key: string
  element_id: number | null
  params: Record<string, unknown>
  output_var: string | null
  timeout_ms: number | null
  on_failure: 'ABORT' | 'CONTINUE' | 'RETRY'
  retry_times: number
  enabled: boolean
  remark: string | null
}

export interface CaseDetail {
  id: number
  project_id: number
  title: string
  description?: string | null
  state: boolean
  created_at?: string | null
  steps: TestStep[]
}

export interface ActionDef {
  action_key: string
  name: string
  category: string
  platforms: string[]
  engines: string[]
  requires_element: boolean
  params_schema: {
    type: string
    properties?: Record<string, Record<string, unknown>>
    required?: string[]
  }
}

export interface Artifact {
  id: number
  execution_id: number
  step_result_id: number | null
  kind: string
  storage: string
  size_bytes: number | null
  created_at: string | null
  url: string
}

// ── 一键接入（M3.4）──────────────────────────────────
export interface ScaffoldResult {
  project: { id: number; code: string; platform: string; engine_key: string; created: boolean }
  target: { id: number; base_url: string; created: boolean }
  elements: {
    key: string; id: number; name: string; created: boolean; locator_ids: number[]
  }[]
  case: {
    id: number; title: string; created: boolean; step_ids: number[]; step_count: number
  }
  suite: { id: number; name: string; created: boolean; case_count: number }
  execution: {
    id: number; status: string; suite_id: number; case_count: number;
    queued_at: string | null
  } | null
  warnings: string[]
  duration_ms: number
}

// ── 页面扫描（M3.5）──────────────────────────────────
export interface ScanLocator {
  locator_type: string
  locator_value: string
  primary: boolean
}

export interface ScanCandidate {
  key: string
  tag: string
  name: string
  text: string
  strength: 'strong' | 'medium' | 'weak'
  locators: ScanLocator[]
}

export interface ScanResult {
  url: string
  candidates: ScanCandidate[]
  stats: {
    total: number
    strong: number
    medium: number
    weak: number
    skipped: number
  }
  warnings: string[]
  duration_ms: number
}

export interface ScanImportResult {
  created: { name: string; element_id: number; locator_ids: number[] }[]
  failed: { name: string; code: string; message: string }[]
}

export interface Execution {
  id: number
  project_id: number
  suite_id?: number | null
  suite_name?: string | null
  status: 'PENDING' | 'RUNNING' | 'PASSED' | 'FAILED' | 'ERROR' | 'CANCELLED'
  platform: Platform
  engine_key: string
  total: number
  passed: number
  failed: number
  errored: number
  skipped: number
  duration_ms: number | null
  message?: string | null
  started_at: string | null
  finished_at: string | null
  cases?: ExecutionCase[]
  progress?: { done_steps: number; total_steps: number | null }
}
