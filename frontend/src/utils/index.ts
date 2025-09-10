import { DataRow, ComputedFieldDefinition } from '@/types'

/**
 * Convert various data types to numbers, handling common edge cases
 * Migrated from legacy num() function
 */
export function toNumber(x: any): number {
  if (x === null || x === undefined || x === '') return 0
  if (typeof x === 'number' && isFinite(x)) return x

  if (typeof x === 'string') {
    let s = x.replace(/\u00A0/g, ' ').trim().replace(/\s+/g, '')
    
    // Handle numbers with both commas and dots
    if (s.includes(',') && s.includes('.')) {
      if (s.lastIndexOf(',') > s.lastIndexOf('.')) {
        // European format: 1.234.567,89
        s = s.replace(/\./g, '').replace(',', '.')
      } else {
        // US format: 1,234,567.89
        s = s.replace(/,/g, '')
      }
    } else if (s.includes(',')) {
      // Only commas - could be thousands separator or decimal
      s = s.replace(/\./g, '').replace(/,/g, '.')
    }
    
    const v = parseFloat(s)
    return isNaN(v) ? 0 : v
  }
  
  const v = Number(x)
  return isNaN(v) ? 0 : v
}

/**
 * Compile expression into executable function
 * Migrated from legacy compileExpr() function
 */
export function compileExpression(
  expr: string,
  computedDefs: ComputedFieldDefinition[] = [],
  iferrEnabled = false,
  iferrFallback = 0
): (row: DataRow) => any {
  return function(r: DataRow): any {
    try {
      // Get all available field names
      const allKeys = [...Object.keys(r), ...computedDefs.map(d => d.name)]
      const keys = [...new Set(allKeys)].sort((a, b) => b.length - a.length)
      
      let code = expr
      
      // Replace field names with safe access patterns
      keys.forEach(k => {
        const parts = code.split(k)
        if (parts.length > 1) {
          let result = parts[0]
          for (let i = 1; i < parts.length; i++) {
            const prevChar = result.slice(-1)
            const nextChar = parts[i].slice(0, 1)
            
            // Check if this is a complete field name (word boundaries)
            const isValidBoundary = (
              (prevChar === '' || !/[A-Za-z0-9_\u4e00-\u9fff]/.test(prevChar)) &&
              (nextChar === '' || !/[A-Za-z0-9_\u4e00-\u9fff]/.test(nextChar))
            )
            
            if (isValidBoundary) {
              result += `toNumber(r["${k}"])` + parts[i]
            } else {
              result += k + parts[i]
            }
          }
          code = result
        }
      })
      
      // Create function with helper functions in scope
      const fn = new Function(
        'r', 'toNumber', '__enabled', '__fb',
        `
          const IFERROR = (v, fb = 0) => {
            const n = Number(v)
            return (Number.isFinite(n) && !Number.isNaN(n)) ? v : fb
          }
          const DIV = (a, b, fb = 0) => {
            const na = toNumber(a)
            const nb = toNumber(b)
            if (nb === 0) return fb
            const q = na / nb
            return (Number.isFinite(q) && !Number.isNaN(q)) ? q : fb
          }
          const _res = (${code})
          return __enabled ? IFERROR(_res, __fb) : _res
        `
      )
      
      return fn(r, toNumber, iferrEnabled, iferrFallback)
    } catch (e) {
      console.warn('Expression compilation error:', e)
      return null
    }
  }
}

/**
 * Extract variable names from expression
 * Migrated from legacy extractVars() function
 */
export function extractVariablesFromExpression(
  expr: string, 
  knownFields: string[] = []
): string[] {
  const vars = new Set<string>()
  
  // Simple regex to find potential variable names
  const matches = expr.match(/[a-zA-Z_\u4e00-\u9fff][a-zA-Z0-9_\u4e00-\u9fff]*/g) || []
  
  matches.forEach(match => {
    // Skip JavaScript keywords and function names
    const keywords = ['if', 'else', 'for', 'while', 'function', 'var', 'let', 'const', 
                     'return', 'true', 'false', 'null', 'undefined', 'IFERROR', 'DIV']
    
    if (!keywords.includes(match) && knownFields.includes(match)) {
      vars.add(match)
    }
  })
  
  return Array.from(vars)
}

/**
 * Format number according to format specification
 */
export function formatNumber(
  value: any,
  format?: {
    type?: 'number' | 'percentage' | 'currency'
    decimals?: number
    prefix?: string
    suffix?: string
  }
): string {
  const num = toNumber(value)
  
  if (!format) {
    return num.toString()
  }
  
  const { type = 'number', decimals = 2, prefix = '', suffix = '' } = format
  
  let formatted: string
  
  switch (type) {
    case 'percentage':
      formatted = (num * 100).toFixed(decimals) + '%'
      break
    case 'currency':
      formatted = '¥' + num.toLocaleString('zh-CN', { 
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals 
      })
      break
    default:
      formatted = num.toLocaleString('zh-CN', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
      })
  }
  
  return prefix + formatted + suffix
}

/**
 * Debounce function for search and input handling
 */
export function debounce<T extends (...args: any[]) => any>(
  func: T,
  wait: number
): (...args: Parameters<T>) => void {
  let timeout: NodeJS.Timeout
  
  return (...args: Parameters<T>) => {
    clearTimeout(timeout)
    timeout = setTimeout(() => func(...args), wait)
  }
}

/**
 * Deep clone object
 */
export function deepClone<T>(obj: T): T {
  if (obj === null || typeof obj !== 'object') return obj
  if (obj instanceof Date) return new Date(obj.getTime()) as any
  if (obj instanceof Array) return obj.map(item => deepClone(item)) as any
  if (obj instanceof Set) return new Set(Array.from(obj).map(item => deepClone(item))) as any
  if (obj instanceof Map) {
    const cloned = new Map()
    obj.forEach((value, key) => {
      cloned.set(deepClone(key), deepClone(value))
    })
    return cloned as any
  }
  
  const cloned: any = {}
  Object.keys(obj).forEach(key => {
    cloned[key] = deepClone((obj as any)[key])
  })
  
  return cloned
}

/**
 * Generate unique ID
 */
export function generateId(prefix = 'id'): string {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
}

/**
 * Check if value is empty
 */
export function isEmpty(value: any): boolean {
  if (value === null || value === undefined) return true
  if (typeof value === 'string') return value.trim() === ''
  if (Array.isArray(value)) return value.length === 0
  if (typeof value === 'object') return Object.keys(value).length === 0
  return false
}

/**
 * Safe JSON parse
 */
export function safeJsonParse<T>(json: string, defaultValue: T): T {
  try {
    return JSON.parse(json)
  } catch {
    return defaultValue
  }
}

/**
 * Download data as CSV
 */
export function downloadCsv(data: any[], filename = 'data.csv'): void {
  if (!data.length) return
  
  const headers = Object.keys(data[0])
  const csvContent = [
    headers.join(','),
    ...data.map(row => 
      headers.map(header => {
        const value = row[header]
        const stringValue = value === null || value === undefined ? '' : String(value)
        // Escape quotes and wrap in quotes if contains comma or quote
        if (stringValue.includes(',') || stringValue.includes('"') || stringValue.includes('\n')) {
          return '"' + stringValue.replace(/"/g, '""') + '"'
        }
        return stringValue
      }).join(',')
    )
  ].join('\n')
  
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  
  URL.revokeObjectURL(url)
}

/**
 * Log function with timestamp
 */
export function createLogger(name: string) {
  return {
    info: (message: string, ...args: any[]) => {
      console.log(`[${new Date().toISOString().substr(11, 8)}] ${name}: ${message}`, ...args)
    },
    error: (message: string, ...args: any[]) => {
      console.error(`[${new Date().toISOString().substr(11, 8)}] ${name}: ${message}`, ...args)
    },
    warn: (message: string, ...args: any[]) => {
      console.warn(`[${new Date().toISOString().substr(11, 8)}] ${name}: ${message}`, ...args)
    }
  }
}