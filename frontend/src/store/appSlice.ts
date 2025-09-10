import { createSlice, PayloadAction } from '@reduxjs/toolkit'
import type { AppState, DataRow, AppConfig, PivotLayout, ComputedFieldDefinition, FieldFormat, RowFieldFilters, MetricFieldFilters } from '@/types'

const initialConfig: AppConfig = {
  apiBase: 'http://localhost:8000',
  collection: '',
  limit: 1000,
  skip: 0,
  filters: {},
  viewMode: 'pivot',
  subtotalEnabled: false,
  iferrDefaultEnabled: false,
  iferrDefaultFallback: 0,
}

const initialState: AppState = {
  // Data management
  rawBaseRows: [],
  currentRows: [],
  rawUploadRows: [],
  filteredRows: [],
  
  // Configuration
  config: initialConfig,
  
  // Field management
  availableFields: [],
  hiddenFields: new Set(),
  layout: { rows: [], cols: [], vals: [] },
  computedDefs: [],
  formats: {},
  
  // Filtering
  rowFieldFilters: {},
  metricFieldFilters: {},
  
  // UI state
  isLoading: false,
  error: null,
  isUploadedMode: false,
  
  // Panel states
  filterPanelVisible: true,
  configPanelVisible: true,
  
  // Table state
  freezeRows: 0,
  freezeCols: 0,
}

export const appSlice = createSlice({
  name: 'app',
  initialState,
  reducers: {
    // Data actions
    setRawBaseRows: (state, action: PayloadAction<DataRow[]>) => {
      state.rawBaseRows = action.payload
      state.currentRows = action.payload
    },
    setCurrentRows: (state, action: PayloadAction<DataRow[]>) => {
      state.currentRows = action.payload
    },
    setRawUploadRows: (state, action: PayloadAction<DataRow[]>) => {
      state.rawUploadRows = action.payload
    },
    setFilteredRows: (state, action: PayloadAction<DataRow[]>) => {
      state.filteredRows = action.payload
    },
    
    // Configuration actions
    updateConfig: (state, action: PayloadAction<Partial<AppConfig>>) => {
      state.config = { ...state.config, ...action.payload }
    },
    
    // Field management actions
    setAvailableFields: (state, action: PayloadAction<string[]>) => {
      state.availableFields = action.payload
    },
    toggleFieldVisibility: (state, action: PayloadAction<string>) => {
      const field = action.payload
      if (state.hiddenFields.has(field)) {
        state.hiddenFields.delete(field)
      } else {
        state.hiddenFields.add(field)
      }
    },
    updateLayout: (state, action: PayloadAction<Partial<PivotLayout>>) => {
      state.layout = { ...state.layout, ...action.payload }
    },
    addComputedField: (state, action: PayloadAction<ComputedFieldDefinition>) => {
      state.computedDefs.push(action.payload)
    },
    removeComputedField: (state, action: PayloadAction<string>) => {
      state.computedDefs = state.computedDefs.filter(def => def.name !== action.payload)
    },
    updateFormats: (state, action: PayloadAction<FieldFormat>) => {
      state.formats = { ...state.formats, ...action.payload }
    },
    
    // Filter actions
    updateRowFieldFilters: (state, action: PayloadAction<RowFieldFilters>) => {
      state.rowFieldFilters = action.payload
    },
    updateMetricFieldFilters: (state, action: PayloadAction<MetricFieldFilters>) => {
      state.metricFieldFilters = action.payload
    },
    clearAllFilters: (state) => {
      state.rowFieldFilters = {}
      state.metricFieldFilters = {}
    },
    
    // UI state actions
    setLoading: (state, action: PayloadAction<boolean>) => {
      state.isLoading = action.payload
    },
    setError: (state, action: PayloadAction<string | null>) => {
      state.error = action.payload
    },
    setUploadedMode: (state, action: PayloadAction<boolean>) => {
      state.isUploadedMode = action.payload
    },
    
    // Panel visibility actions
    toggleFilterPanel: (state) => {
      state.filterPanelVisible = !state.filterPanelVisible
    },
    toggleConfigPanel: (state) => {
      state.configPanelVisible = !state.configPanelVisible
    },
    setFilterPanelVisible: (state, action: PayloadAction<boolean>) => {
      state.filterPanelVisible = action.payload
    },
    setConfigPanelVisible: (state, action: PayloadAction<boolean>) => {
      state.configPanelVisible = action.payload
    },
    
    // Table state actions
    updateFreezeSettings: (state, action: PayloadAction<{rows: number, cols: number}>) => {
      state.freezeRows = action.payload.rows
      state.freezeCols = action.payload.cols
    },
  },
})

export const {
  setRawBaseRows,
  setCurrentRows,
  setRawUploadRows,
  setFilteredRows,
  updateConfig,
  setAvailableFields,
  toggleFieldVisibility,
  updateLayout,
  addComputedField,
  removeComputedField,
  updateFormats,
  updateRowFieldFilters,
  updateMetricFieldFilters,
  clearAllFilters,
  setLoading,
  setError,
  setUploadedMode,
  toggleFilterPanel,
  toggleConfigPanel,
  setFilterPanelVisible,
  setConfigPanelVisible,
  updateFreezeSettings,
} = appSlice.actions