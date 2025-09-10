// Core data types based on existing system
export interface DataRow {
  [key: string]: any
}

export interface ComputedFieldDefinition {
  name: string
  expr: string
  vars?: string[]
}

export interface PivotLayout {
  rows: string[]
  cols: string[]
  vals: string[]
}

export interface FieldFormat {
  [fieldName: string]: {
    type?: 'number' | 'percentage' | 'currency'
    decimals?: number
    prefix?: string
    suffix?: string
  }
}

export interface FilterDefinition {
  field: string
  operator: 'equals' | 'contains' | 'startsWith' | 'gt' | 'lt' | 'gte' | 'lte' | 'in'
  value: any
  values?: any[]
}

export interface RowFieldFilters {
  [fieldName: string]: FilterDefinition[]
}

export interface MetricFieldFilters {
  [fieldName: string]: FilterDefinition[]
}

// API types
export interface ApiHealthResponse {
  status: string
  timestamp?: string
}

export interface ApiCollectionsResponse {
  collections: string[]
}

export interface ApiDataResponse {
  data: DataRow[]
  total?: number
  success: boolean
  message?: string
}

// Application state types
export interface AppConfig {
  apiBase: string
  collection: string
  limit: number
  skip: number
  filters: Record<string, any>
  viewMode: 'pivot' | 'raw'
  subtotalEnabled: boolean
  iferrDefaultEnabled: boolean
  iferrDefaultFallback: number
}

export interface AppState {
  // Data management
  rawBaseRows: DataRow[]
  currentRows: DataRow[]
  rawUploadRows: DataRow[]
  filteredRows: DataRow[]
  
  // Configuration
  config: AppConfig
  
  // Field management
  availableFields: string[]
  hiddenFields: Set<string>
  layout: PivotLayout
  computedDefs: ComputedFieldDefinition[]
  formats: FieldFormat
  
  // Filtering
  rowFieldFilters: RowFieldFilters
  metricFieldFilters: MetricFieldFilters
  
  // UI state
  isLoading: boolean
  error: string | null
  isUploadedMode: boolean
  
  // Panel states
  filterPanelVisible: boolean
  configPanelVisible: boolean
  
  // Table state
  freezeRows: number
  freezeCols: number
}

// Cloud configuration types
export interface CloudProfile {
  name: string
  config: Partial<AppState>
  timestamp: string
}

// File upload types
export interface FileUploadOptions {
  file: File
  sheetName?: string
  startRow?: number
}

// Component prop types
export interface PivotTableProps {
  data: DataRow[]
  layout: PivotLayout
  formats: FieldFormat
  subtotalEnabled: boolean
  freezeRows: number
  freezeCols: number
  onCellClick?: (row: number, col: number, value: any) => void
}

export interface FieldZoneProps {
  title: string
  fields: string[]
  availableFields: string[]
  onFieldsChange: (fields: string[]) => void
  allowMultiple?: boolean
  acceptedTypes?: ('dimension' | 'measure')[]
}

export interface FilterPanelProps {
  visible: boolean
  onVisibilityChange: (visible: boolean) => void
  rowFieldFilters: RowFieldFilters
  metricFieldFilters: MetricFieldFilters
  onFiltersChange: (rowFilters: RowFieldFilters, metricFilters: MetricFieldFilters) => void
}

export interface ConfigPanelProps {
  visible: boolean
  onVisibilityChange: (visible: boolean) => void
  config: AppConfig
  onConfigChange: (config: Partial<AppConfig>) => void
  availableCollections: string[]
  healthStatus: 'ok' | 'error' | 'checking'
}

// Utility types
export type DragEndResult = {
  source: {
    droppableId: string
    index: number
  }
  destination: {
    droppableId: string
    index: number
  } | null
  draggableId: string
}

export type AggregationType = 'sum' | 'count' | 'avg' | 'min' | 'max' | 'first' | 'last'

export interface AggregationConfig {
  field: string
  type: AggregationType
  label?: string
}

// Error types
export class AppError extends Error {
  constructor(
    message: string,
    public code?: string,
    public details?: any
  ) {
    super(message)
    this.name = 'AppError'
  }
}