import React, { useState, useMemo } from 'react'
import {
  Box,
  Typography,
  Paper,
  Grid,
  Chip,
  Card,
  CardContent,
  CardHeader,
  Button,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  TextField,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Divider,
  List,
  ListItem,
  ListItemText,
  ListItemSecondaryAction,
  Checkbox,
  FormControlLabel,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Tabs,
  Tab
} from '@mui/material'
import {
  Delete as DeleteIcon,
  Add as AddIcon,
  Settings as SettingsIcon,
  Calculate as CalculateIcon,
  Save as SaveIcon,
  FolderOpen as LoadIcon,
  ExpandMore as ExpandMoreIcon,
  FormatListNumbered as FormatIcon
} from '@mui/icons-material'
import { DragDropContext, Droppable, Draggable, DropResult } from 'react-beautiful-dnd'

// 聚合方式类型
type AggregationType = 'sum' | 'avg' | 'count' | 'max' | 'min' | 'first' | 'last' | 'computed'

// 数值格式类型
type FormatType = 'number' | 'currency' | 'percentage' | 'decimal1' | 'decimal2' | 'decimal3'

// 字段配置接口
interface FieldConfig {
  field: string
  aggregation?: AggregationType
  alias?: string
  format?: FormatType
}

// 自定义计算字段
interface ComputedField {
  name: string
  formula: string
  alias: string
  format?: FormatType
}

// 透视表配置
interface PivotConfig {
  name?: string
  rowFields: FieldConfig[]
  colFields: FieldConfig[]
  valueFields: FieldConfig[]
  computedFields: ComputedField[]
}

interface EnhancedPivotLayoutProps {
  data?: any[]
  availableFields?: string[]
  fieldTypes?: Record<string, string>
  onPivotUpdate?: (pivotResult: any) => void
}

const AGGREGATION_OPTIONS: { value: AggregationType; label: string }[] = [
  { value: 'sum', label: '求和' },
  { value: 'avg', label: '平均值' },
  { value: 'count', label: '计数' },
  { value: 'max', label: '最大值' },
  { value: 'min', label: '最小值' },
  { value: 'first', label: '第一个' },
  { value: 'last', label: '最后一个' },
  { value: 'computed', label: '自定义计算' }
]

const FORMAT_OPTIONS: { value: FormatType; label: string; example: string }[] = [
  { value: 'number', label: '整数', example: '1,234' },
  { value: 'decimal1', label: '小数(1位)', example: '1,234.5' },
  { value: 'decimal2', label: '小数(2位)', example: '1,234.56' },
  { value: 'decimal3', label: '小数(3位)', example: '1,234.567' },
  { value: 'percentage', label: '百分比', example: '12.34%' },
  { value: 'currency', label: '货币', example: '¥1,234.56' }
]

// 预设的自定义字段模板
const COMPUTED_FIELD_TEMPLATES = [
  {
    name: 'CTR',
    formula: 'clicks / views',
    alias: 'CTR',
    description: '点击率 = 点击数 / 展示数'
  },
  {
    name: 'CPC',
    formula: 'moneySpent / clicks',
    alias: 'CPC',
    description: '点击单价 = 花费 / 点击数'
  },
  {
    name: 'CPM',
    formula: 'moneySpent / views * 1000',
    alias: 'CPM',
    description: '千次展示成本 = 花费 / 展示数 * 1000'
  },
  {
    name: '总订单',
    formula: 'orders + models',
    alias: 'totalOrders',
    description: '总订单 = 普通订单 + 模型订单'
  },
  {
    name: '利润',
    formula: 'revenue - moneySpent',
    alias: 'profit',
    description: '利润 = 收入 - 花费'
  },
  {
    name: '利润率',
    formula: '(revenue - moneySpent) / revenue',
    alias: 'profitRate',
    description: '利润率 = (收入 - 花费) / 收入'
  },
  {
    name: '转化率',
    formula: 'orders / clicks',
    alias: 'conversionRate',
    description: '转化率 = 订单数 / 点击数'
  },
  {
    name: '客单价',
    formula: 'revenue / orders',
    alias: 'avgOrderValue',
    description: '客单价 = 收入 / 订单数'
  },
  {
    name: '效果评分',
    formula: 'clicks > 1000 ? 1 : 0',
    alias: 'performanceScore',
    description: '效果评分 = 点击数 > 1000 ? 优秀 : 一般'
  },
  {
    name: '最大展示',
    formula: 'max(clicks, views)',
    alias: 'maxEngagement',
    description: '最大指标 = max(点击数, 展示数)'
  },
  {
    name: '平均指标',
    formula: '(clicks + views) / 2',
    alias: 'avgMetric',
    description: '平均指标 = (点击数 + 展示数) / 2'
  },
  {
    name: '成本占比',
    formula: 'round(moneySpent / revenue * 100, 2)',
    alias: 'costRatio',
    description: '成本占比 = round(花费/收入*100, 2位小数)'
  }
]

export const EnhancedPivotLayout: React.FC<EnhancedPivotLayoutProps> = ({
  data = [],
  availableFields = [],
  fieldTypes = {},
  onPivotUpdate = () => {}
}) => {
  const [config, setConfig] = useState<PivotConfig>({
    rowFields: [],
    colFields: [],
    valueFields: [],
    computedFields: []
  })

  const [computedDialogOpen, setComputedDialogOpen] = useState(false)
  const [formatDialogOpen, setFormatDialogOpen] = useState(false)
  const [saveDialogOpen, setSaveDialogOpen] = useState(false)
  const [loadDialogOpen, setLoadDialogOpen] = useState(false)

  const [newComputedField, setNewComputedField] = useState<ComputedField>({
    name: '',
    formula: '',
    alias: '',
    format: 'decimal2'
  })

  const [configName, setConfigName] = useState('')
  const [savedConfigs, setSavedConfigs] = useState<PivotConfig[]>([
    // 示例预设配置
    {
      name: 'operation_report基础分析',
      rowFields: [{ field: 'date' }],
      colFields: [],
      valueFields: [
        { field: 'views', aggregation: 'sum' as AggregationType },
        { field: 'clicks', aggregation: 'sum' as AggregationType },
        { field: 'moneySpent', aggregation: 'sum' as AggregationType }
      ],
      computedFields: [
        { name: 'CTR', formula: 'clicks / views', alias: 'CTR', format: 'percentage' as FormatType }
      ]
    }
  ])

  const [activeComputedTab, setActiveComputedTab] = useState(0)

  // 处理拖拽结果
  const onDragEnd = (result: DropResult) => {
    const { source, destination } = result

    if (!destination) return

    // 从可用字段拖拽到配置区域
    if (source.droppableId === 'available-fields') {
      let fieldName: string
      let isComputed = false
      
      const safeAvailableFields = availableFields || []
      if (source.index < safeAvailableFields.length) {
        // 普通字段
        fieldName = safeAvailableFields[source.index]
      } else {
        // 自定义字段
        const computedIndex = source.index - safeAvailableFields.length
        fieldName = (config.computedFields || [])[computedIndex]?.alias || ''
        isComputed = true
      }
      
      const newField: FieldConfig = {
        field: fieldName,
        aggregation: destination.droppableId === 'value-fields' ? (isComputed ? 'computed' as AggregationType : 'sum') : undefined,
        format: isComputed ? config.computedFields.find(c => c.alias === fieldName)?.format || 'decimal2' : 'number'
      }

      setConfig(prev => {
        const newConfig = { ...prev }
        if (destination.droppableId === 'row-fields') {
          newConfig.rowFields = [...prev.rowFields, newField]
        } else if (destination.droppableId === 'col-fields') {
          newConfig.colFields = [...prev.colFields, newField]
        } else if (destination.droppableId === 'value-fields') {
          newConfig.valueFields = [...prev.valueFields, newField]
        }
        return newConfig
      })
      return
    }

    // 在配置区域内重新排序
    const sourceArray = getFieldArray(source.droppableId)
    const destArray = getFieldArray(destination.droppableId)

    if (source.droppableId === destination.droppableId) {
      // 同一区域内重新排序
      const newArray = Array.from(sourceArray)
      const [reorderedItem] = newArray.splice(source.index, 1)
      newArray.splice(destination.index, 0, reorderedItem)

      setConfig(prev => ({
        ...prev,
        [getFieldArrayKey(destination.droppableId)]: newArray
      }))
    } else {
      // 不同区域间移动
      const sourceItems = Array.from(sourceArray)
      const destItems = Array.from(destArray)
      const [movedItem] = sourceItems.splice(source.index, 1)

      // 如果移动到值字段，确保有聚合方式
      if (destination.droppableId === 'value-fields' && !movedItem.aggregation) {
        movedItem.aggregation = 'sum'
      }

      destItems.splice(destination.index, 0, movedItem)

      setConfig(prev => ({
        ...prev,
        [getFieldArrayKey(source.droppableId)]: sourceItems,
        [getFieldArrayKey(destination.droppableId)]: destItems
      }))
    }
  }

  const getFieldArray = (droppableId: string): FieldConfig[] => {
    switch (droppableId) {
      case 'row-fields': return config.rowFields
      case 'col-fields': return config.colFields
      case 'value-fields': return config.valueFields
      default: return []
    }
  }

  const getFieldArrayKey = (droppableId: string): keyof PivotConfig => {
    switch (droppableId) {
      case 'row-fields': return 'rowFields'
      case 'col-fields': return 'colFields'
      case 'value-fields': return 'valueFields'
      default: return 'rowFields'
    }
  }

  // 移除字段
  const removeField = (droppableId: string, index: number) => {
    setConfig(prev => ({
      ...prev,
      [getFieldArrayKey(droppableId)]: getFieldArray(droppableId).filter((_, i) => i !== index)
    }))
  }

  // 更新聚合方式
  const updateAggregation = (droppableId: string, index: number, aggregation: AggregationType) => {
    setConfig(prev => {
      const newArray = [...getFieldArray(droppableId)]
      newArray[index] = { ...newArray[index], aggregation }
      return {
        ...prev,
        [getFieldArrayKey(droppableId)]: newArray
      }
    })
  }

  // 安全除法计算
  const safeDivide = (a: number, b: number): number => {
    return b === 0 ? 0 : a / b
  }

  // 安全的数学运算函数
  const safeMath = {
    add: (a: number, b: number) => a + b,
    subtract: (a: number, b: number) => a - b,
    multiply: (a: number, b: number) => a * b,
    divide: (a: number, b: number) => b === 0 ? 0 : a / b,
    power: (a: number, b: number) => Math.pow(a, b),
    mod: (a: number, b: number) => b === 0 ? 0 : a % b,
    abs: (a: number) => Math.abs(a),
    max: (a: number, b: number) => Math.max(a, b),
    min: (a: number, b: number) => Math.min(a, b),
    round: (a: number, digits: number = 0) => Math.round(a * Math.pow(10, digits)) / Math.pow(10, digits)
  }

  // 计算汇总行的自定义字段值
  const calculateAggregatedComputedValue = (formula: string, aggregatedData: any): number => {
    try {
      let expression = formula.toLowerCase()
      
      // 使用聚合后的数据替换字段名
      Object.keys(aggregatedData).forEach(field => {
        const regex = new RegExp(`\\b${field.toLowerCase()}\\b`, 'g')
        const value = parseFloat(aggregatedData[field]) || 0
        expression = expression.replace(regex, String(value))
      })

      // 处理数学函数和运算符
      expression = expression
        // 处理数学函数
        .replace(/abs\(([^)]+)\)/g, (match, num) => String(Math.abs(parseFloat(num) || 0)))
        .replace(/max\(([^,]+),([^)]+)\)/g, (match, a, b) => String(Math.max(parseFloat(a) || 0, parseFloat(b) || 0)))
        .replace(/min\(([^,]+),([^)]+)\)/g, (match, a, b) => String(Math.min(parseFloat(a) || 0, parseFloat(b) || 0)))
        .replace(/round\(([^,)]+)(?:,([^)]+))?\)/g, (match, num, digits) => {
          const n = parseFloat(num) || 0
          const d = parseInt(digits) || 0
          return String(Math.round(n * Math.pow(10, d)) / Math.pow(10, d))
        })
        .replace(/pow\(([^,]+),([^)]+)\)/g, (match, base, exp) => String(Math.pow(parseFloat(base) || 0, parseFloat(exp) || 0)))
        
        // 处理安全除法 - 确保分母不为0
        .replace(/(\d+(?:\.\d+)?)\s*\/\s*(\d+(?:\.\d+)?)/g, (match, a, b) => {
          const aVal = parseFloat(a) || 0
          const bVal = parseFloat(b) || 0
          return String(bVal === 0 ? 0 : aVal / bVal)
        })
        
        // 处理取模运算 - 确保分母不为0
        .replace(/(\d+(?:\.\d+)?)\s*%\s*(\d+(?:\.\d+)?)/g, (match, a, b) => {
          const aVal = parseFloat(a) || 0
          const bVal = parseFloat(b) || 0
          return String(bVal === 0 ? 0 : aVal % bVal)
        })
        
        // 处理幂运算
        .replace(/(\d+(?:\.\d+)?)\s*\*\*\s*(\d+(?:\.\d+)?)/g, (match, base, exp) => {
          return String(Math.pow(parseFloat(base) || 0, parseFloat(exp) || 0))
        })

      // 处理逻辑运算符 (返回数字: true=1, false=0)
      expression = expression
        .replace(/(\d+(?:\.\d+)?)\s*>\s*(\d+(?:\.\d+)?)/g, (match, a, b) => {
          return String((parseFloat(a) || 0) > (parseFloat(b) || 0) ? 1 : 0)
        })
        .replace(/(\d+(?:\.\d+)?)\s*<\s*(\d+(?:\.\d+)?)/g, (match, a, b) => {
          return String((parseFloat(a) || 0) < (parseFloat(b) || 0) ? 1 : 0)
        })
        .replace(/(\d+(?:\.\d+)?)\s*>=\s*(\d+(?:\.\d+)?)/g, (match, a, b) => {
          return String((parseFloat(a) || 0) >= (parseFloat(b) || 0) ? 1 : 0)
        })
        .replace(/(\d+(?:\.\d+)?)\s*<=\s*(\d+(?:\.\d+)?)/g, (match, a, b) => {
          return String((parseFloat(a) || 0) <= (parseFloat(b) || 0) ? 1 : 0)
        })
        .replace(/(\d+(?:\.\d+)?)\s*==\s*(\d+(?:\.\d+)?)/g, (match, a, b) => {
          return String((parseFloat(a) || 0) === (parseFloat(b) || 0) ? 1 : 0)
        })
        .replace(/(\d+(?:\.\d+)?)\s*!=\s*(\d+(?:\.\d+)?)/g, (match, a, b) => {
          return String((parseFloat(a) || 0) !== (parseFloat(b) || 0) ? 1 : 0)
        })

      // 处理三元运算符：条件 ? 真值 : 假值
      expression = expression.replace(/(\d+(?:\.\d+)?)\s*\?\s*(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)/g, (match, condition, trueVal, falseVal) => {
        const cond = parseFloat(condition) || 0
        const tVal = parseFloat(trueVal) || 0  
        const fVal = parseFloat(falseVal) || 0
        return String(cond !== 0 ? tVal : fVal)
      })

      // 使用Function构造器安全计算
      const result = new Function('return ' + expression)()
      return isNaN(result) ? 0 : result
    } catch (error) {
      console.warn('汇总计算公式错误:', formula, error)
      return 0
    }
  }

  // 计算自定义字段值 (行级别计算，直接使用汇总计算逻辑)
  const calculateComputedValue = (formula: string, row: any): number => {
    return calculateAggregatedComputedValue(formula, row)
  }

  // 格式化数值
  const formatValue = (value: number, format: FormatType = 'number'): string => {
    if (value === null || value === undefined || isNaN(value)) return '0'
    
    switch (format) {
      case 'currency':
        return '¥' + value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
      case 'percentage':
        return (value * 100).toFixed(2) + '%'
      case 'decimal1':
        return value.toLocaleString('zh-CN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
      case 'decimal2':
        return value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
      case 'decimal3':
        return value.toLocaleString('zh-CN', { minimumFractionDigits: 3, maximumFractionDigits: 3 })
      case 'number':
      default:
        return Math.round(value).toLocaleString('zh-CN')
    }
  }

  // 提取公式中依赖的字段名
  const extractFieldsFromFormula = (formula: string): string[] => {
    const fields: string[] = []
    // 匹配所有可能是字段名的标识符（字母开头，可包含字母、数字、下划线）
    const fieldMatches = formula.match(/\b[a-zA-Z_][a-zA-Z0-9_]*\b/g) || []
    
    fieldMatches.forEach(field => {
      // 排除数学函数名和保留字
      const reservedWords = ['abs', 'max', 'min', 'round', 'pow', 'true', 'false']
      if (!reservedWords.includes(field.toLowerCase()) && !fields.includes(field.toLowerCase())) {
        fields.push(field.toLowerCase())
      }
    })
    
    return fields
  }

  // 执行透视表计算
  const generatePivotTable = useMemo(() => {
    if (data.length === 0) return null

    // 添加计算字段到数据
    const enrichedData = data.map(row => {
      const newRow = { ...row }
      config.computedFields.forEach(computed => {
        newRow[computed.alias || computed.name] = calculateComputedValue(computed.formula, row)
      })
      return newRow
    })

    // 透视表聚合逻辑
    const rowFieldNames = config.rowFields.map(f => f.field)
    const colFieldNames = config.colFields.map(f => f.field)
    let valueFieldConfigs = [...config.valueFields]

    // 自动添加自定义字段依赖的基础字段到聚合列表
    config.valueFields.forEach(valueField => {
      if (valueField.aggregation === 'computed') {
        const computedField = config.computedFields.find(c => c.alias === valueField.field)
        if (computedField) {
          const dependentFields = extractFieldsFromFormula(computedField.formula)
          
          dependentFields.forEach(depField => {
            // 检查是否已存在该字段的聚合配置
            const exists = valueFieldConfigs.some(vf => vf.field.toLowerCase() === depField.toLowerCase())
            
            if (!exists) {
              // 自动添加依赖字段（默认使用sum聚合）
              valueFieldConfigs.push({
                field: depField,
                aggregation: 'sum' as AggregationType,
                format: 'number' as FormatType
              })
            }
          })
        }
      }
    })

    if (rowFieldNames.length === 0 && colFieldNames.length === 0) {
      return null
    }

    // 基本的透视表数据结构
    const pivotData: any = {}
    const colTotals: any = {}
    let grandTotal: any = {}

    // 初始化汇总
    valueFieldConfigs.forEach(valueField => {
      grandTotal[valueField.field] = 0
    })

    enrichedData.forEach(row => {
      const rowKey = rowFieldNames.map(field => row[field] || 'null').join('|')
      const colKey = colFieldNames.map(field => row[field] || 'null').join('|')

      if (!pivotData[rowKey]) {
        pivotData[rowKey] = {}
      }

      if (!pivotData[rowKey][colKey]) {
        pivotData[rowKey][colKey] = {}
        valueFieldConfigs.forEach(valueField => {
          // 自定义字段初始化为null，普通字段初始化为0
          pivotData[rowKey][colKey][valueField.field] = valueField.aggregation === 'computed' ? null : 0
        })
      }

      if (!colTotals[colKey]) {
        colTotals[colKey] = {}
        valueFieldConfigs.forEach(valueField => {
          colTotals[colKey][valueField.field] = 0
        })
      }

      // 聚合计算
      valueFieldConfigs.forEach(valueField => {
        const aggregation = valueField.aggregation || 'sum'

        if (aggregation === 'computed') {
          // 自定义字段：需要先聚合基础数据，然后基于聚合结果计算
          // 这里我们不直接计算，而是让后续逻辑处理
          // 我们需要确保自定义字段所依赖的基础字段已经被聚合
        } else {
          // 普通字段
          const value = parseFloat(row[valueField.field]) || 0
          
          switch (aggregation) {
            case 'sum':
              pivotData[rowKey][colKey][valueField.field] += value
              colTotals[colKey][valueField.field] += value
              grandTotal[valueField.field] += value
              break
            case 'count':
              pivotData[rowKey][colKey][valueField.field] += 1
              colTotals[colKey][valueField.field] += 1
              grandTotal[valueField.field] += 1
              break
            default:
              pivotData[rowKey][colKey][valueField.field] += value
          }
        }
      })
    })

    // 计算汇总行中的自定义字段值
    const computedFieldsInValues = valueFieldConfigs.filter(field => field.aggregation === 'computed')
    
    if (computedFieldsInValues.length > 0) {
      // 为列汇总计算自定义字段
      Object.keys(colTotals).forEach(colKey => {
        computedFieldsInValues.forEach(valueField => {
          const computedField = config.computedFields.find(c => c.alias === valueField.field)
          if (computedField) {
            colTotals[colKey][valueField.field] = calculateAggregatedComputedValue(
              computedField.formula,
              colTotals[colKey]
            )
          }
        })
      })
      
      // 为总汇总计算自定义字段
      computedFieldsInValues.forEach(valueField => {
        const computedField = config.computedFields.find(c => c.alias === valueField.field)
        if (computedField) {
          grandTotal[valueField.field] = calculateAggregatedComputedValue(
            computedField.formula,
            grandTotal
          )
        }
      })
    }

    // 为每个单元格重新计算自定义字段（基于聚合后的数据）
    if (computedFieldsInValues.length > 0) {
      Object.keys(pivotData).forEach(rowKey => {
        Object.keys(pivotData[rowKey]).forEach(colKey => {
          computedFieldsInValues.forEach(valueField => {
            const computedField = config.computedFields.find(c => c.alias === valueField.field)
            if (computedField) {
              // 使用该单元格的聚合数据重新计算自定义字段
              const cellData = pivotData[rowKey][colKey]
              const computedValue = calculateAggregatedComputedValue(
                computedField.formula,
                cellData
              )
              pivotData[rowKey][colKey][valueField.field] = computedValue
            }
          })
        })
      })
    }

    return {
      data: pivotData,
      colTotals,
      grandTotal,
      rowFields: rowFieldNames,
      colFields: colFieldNames,
      valueFields: valueFieldConfigs
    }
  }, [data, config])

  // 添加自定义字段
  const addComputedField = () => {
    if (!newComputedField.name || !newComputedField.formula) return

    setConfig(prev => ({
      ...prev,
      computedFields: [...prev.computedFields, { ...newComputedField }]
    }))

    setNewComputedField({ name: '', formula: '', alias: '', format: 'decimal2' })
    setComputedDialogOpen(false)
  }

  // 使用模板创建自定义字段
  const useComputedTemplate = (template: typeof COMPUTED_FIELD_TEMPLATES[0]) => {
    setNewComputedField({
      name: template.name,
      formula: template.formula,
      alias: template.alias,
      format: 'decimal2'
    })
  }

  // 保存配置
  const saveConfig = () => {
    if (!configName) return
    
    const newConfig = {
      ...config,
      name: configName
    }
    
    setSavedConfigs(prev => {
      const existingIndex = prev.findIndex(c => c.name === configName)
      if (existingIndex >= 0) {
        const updated = [...prev]
        updated[existingIndex] = newConfig
        return updated
      } else {
        return [...prev, newConfig]
      }
    })
    
    setConfigName('')
    setSaveDialogOpen(false)
  }

  // 加载配置
  const loadConfig = (savedConfig: PivotConfig) => {
    setConfig({
      rowFields: savedConfig.rowFields || [],
      colFields: savedConfig.colFields || [],
      valueFields: savedConfig.valueFields || [],
      computedFields: savedConfig.computedFields || []
    })
    setLoadDialogOpen(false)
  }

  // 生成透视表
  const handleGeneratePivot = () => {
    const result = generatePivotTable
    onPivotUpdate(result)
  }

  // 只有当availableFields准备好时才渲染拖拽组件
  if (!availableFields || availableFields.length === 0) {
    return (
      <Box p={2} textAlign="center">
        <Typography color="text.secondary">
          等待数据加载...
        </Typography>
      </Box>
    )
  }

  return (
    <DragDropContext 
      onDragEnd={onDragEnd}
      key="pivot-drag-drop-context"
    >
      <Box>
        {/* 工具栏 */}
        <Box mb={2} display="flex" gap={1} alignItems="center">
          <Button
            startIcon={<SaveIcon />}
            variant="outlined"
            size="small"
            onClick={() => setSaveDialogOpen(true)}
          >
            保存配置
          </Button>
          <Button
            startIcon={<LoadIcon />}
            variant="outlined"
            size="small"
            onClick={() => setLoadDialogOpen(true)}
          >
            加载配置
          </Button>
          <Button
            startIcon={<FormatIcon />}
            variant="outlined"
            size="small"
            onClick={() => setFormatDialogOpen(true)}
          >
            指标格式
          </Button>
        </Box>

        <Grid container spacing={3}>
          {/* 可用字段 */}
          <Grid item xs={12} md={3}>
            <Card>
              <CardHeader 
                title="可用字段" 
                action={
                  <IconButton onClick={() => setComputedDialogOpen(true)} size="small">
                    <CalculateIcon />
                  </IconButton>
                }
              />
              <CardContent>
                <Droppable droppableId="available-fields" isDropDisabled>
                  {(provided) => (
                    <Box
                      ref={provided.innerRef}
                      {...provided.droppableProps}
                      display="flex"
                      flexDirection="column"
                      gap={1}
                      minHeight={200}
                    >
                      {(availableFields || []).map((field, index) => (
                        <Draggable key={field} draggableId={field} index={index}>
                          {(provided, snapshot) => (
                            <Chip
                              ref={provided.innerRef}
                              {...provided.draggableProps}
                              {...provided.dragHandleProps}
                              label={`${field} (${fieldTypes[field] || 'unknown'})`}
                              variant="outlined"
                              size="small"
                              sx={{
                                cursor: 'grab',
                                opacity: snapshot.isDragging ? 0.5 : 1,
                                alignSelf: 'flex-start'
                              }}
                            />
                          )}
                        </Draggable>
                      ))}
                      {/* 自定义字段 */}
                      {(config.computedFields || []).map((computed, index) => (
                        <Draggable 
                          key={`computed-${computed.alias}`} 
                          draggableId={`computed-${computed.alias}`} 
                          index={(availableFields || []).length + index}
                        >
                          {(provided, snapshot) => (
                            <Chip
                              ref={provided.innerRef}
                              {...provided.draggableProps}
                              {...provided.dragHandleProps}
                              label={`${computed.alias} (自定义)`}
                              variant="filled"
                              size="small"
                              color="secondary"
                              sx={{
                                cursor: 'grab',
                                opacity: snapshot.isDragging ? 0.5 : 1,
                                alignSelf: 'flex-start'
                              }}
                            />
                          )}
                        </Draggable>
                      ))}
                      {provided.placeholder}
                    </Box>
                  )}
                </Droppable>
              </CardContent>
            </Card>
          </Grid>

          {/* 透视配置 */}
          <Grid item xs={12} md={9}>
            <Grid container spacing={2}>
              {/* 行字段 */}
              <Grid item xs={12} md={4}>
                <Card>
                  <CardHeader title="行字段" />
                  <CardContent>
                    <Droppable droppableId="row-fields">
                      {(provided, snapshot) => (
                        <Box
                          ref={provided.innerRef}
                          {...provided.droppableProps}
                          minHeight={120}
                          bgcolor={snapshot.isDraggingOver ? 'action.hover' : 'transparent'}
                          borderRadius={1}
                          p={1}
                          border="2px dashed"
                          borderColor={snapshot.isDraggingOver ? 'primary.main' : 'divider'}
                        >
                          {config.rowFields.map((fieldConfig, index) => (
                            <Draggable key={`row-${fieldConfig.field}`} draggableId={`row-${fieldConfig.field}`} index={index}>
                              {(provided) => (
                                <Box
                                  ref={provided.innerRef}
                                  {...provided.draggableProps}
                                  {...provided.dragHandleProps}
                                  display="flex"
                                  alignItems="center"
                                  gap={1}
                                  mb={1}
                                  p={1}
                                  bgcolor="background.paper"
                                  borderRadius={1}
                                  boxShadow={1}
                                >
                                  <Typography variant="body2" flex={1}>
                                    {fieldConfig.field}
                                  </Typography>
                                  <IconButton size="small" onClick={() => removeField('row-fields', index)}>
                                    <DeleteIcon fontSize="small" />
                                  </IconButton>
                                </Box>
                              )}
                            </Draggable>
                          ))}
                          {provided.placeholder}
                          {config.rowFields.length === 0 && (
                            <Typography variant="body2" color="text.secondary" textAlign="center">
                              将字段拖放到这里作为行字段
                            </Typography>
                          )}
                        </Box>
                      )}
                    </Droppable>
                  </CardContent>
                </Card>
              </Grid>

              {/* 列字段 */}
              <Grid item xs={12} md={4}>
                <Card>
                  <CardHeader title="列字段" />
                  <CardContent>
                    <Droppable droppableId="col-fields">
                      {(provided, snapshot) => (
                        <Box
                          ref={provided.innerRef}
                          {...provided.droppableProps}
                          minHeight={120}
                          bgcolor={snapshot.isDraggingOver ? 'action.hover' : 'transparent'}
                          borderRadius={1}
                          p={1}
                          border="2px dashed"
                          borderColor={snapshot.isDraggingOver ? 'primary.main' : 'divider'}
                        >
                          {config.colFields.map((fieldConfig, index) => (
                            <Draggable key={`col-${fieldConfig.field}`} draggableId={`col-${fieldConfig.field}`} index={index}>
                              {(provided) => (
                                <Box
                                  ref={provided.innerRef}
                                  {...provided.draggableProps}
                                  {...provided.dragHandleProps}
                                  display="flex"
                                  alignItems="center"
                                  gap={1}
                                  mb={1}
                                  p={1}
                                  bgcolor="background.paper"
                                  borderRadius={1}
                                  boxShadow={1}
                                >
                                  <Typography variant="body2" flex={1}>
                                    {fieldConfig.field}
                                  </Typography>
                                  <IconButton size="small" onClick={() => removeField('col-fields', index)}>
                                    <DeleteIcon fontSize="small" />
                                  </IconButton>
                                </Box>
                              )}
                            </Draggable>
                          ))}
                          {provided.placeholder}
                          {config.colFields.length === 0 && (
                            <Typography variant="body2" color="text.secondary" textAlign="center">
                              将字段拖放到这里作为列字段
                            </Typography>
                          )}
                        </Box>
                      )}
                    </Droppable>
                  </CardContent>
                </Card>
              </Grid>

              {/* 指标字段 */}
              <Grid item xs={12} md={4}>
                <Card>
                  <CardHeader title="指标 (聚合)" />
                  <CardContent>
                    <Droppable droppableId="value-fields">
                      {(provided, snapshot) => (
                        <Box
                          ref={provided.innerRef}
                          {...provided.droppableProps}
                          minHeight={120}
                          bgcolor={snapshot.isDraggingOver ? 'action.hover' : 'transparent'}
                          borderRadius={1}
                          p={1}
                          border="2px dashed"
                          borderColor={snapshot.isDraggingOver ? 'primary.main' : 'divider'}
                        >
                          {config.valueFields.map((fieldConfig, index) => (
                            <Draggable key={`value-${fieldConfig.field}`} draggableId={`value-${fieldConfig.field}`} index={index}>
                              {(provided) => (
                                <Box
                                  ref={provided.innerRef}
                                  {...provided.draggableProps}
                                  {...provided.dragHandleProps}
                                  display="flex"
                                  alignItems="center"
                                  gap={1}
                                  mb={1}
                                  p={1}
                                  bgcolor="background.paper"
                                  borderRadius={1}
                                  boxShadow={1}
                                >
                                  <Typography variant="body2" flex={1}>
                                    {fieldConfig.field}
                                  </Typography>
                                  {fieldConfig.aggregation === 'computed' ? (
                                    <Chip size="small" label="自定义" color="secondary" />
                                  ) : (
                                    <FormControl size="small" sx={{ minWidth: 80 }}>
                                      <Select
                                        value={fieldConfig.aggregation || 'sum'}
                                        onChange={(e) => updateAggregation('value-fields', index, e.target.value as AggregationType)}
                                        size="small"
                                      >
                                        {AGGREGATION_OPTIONS.filter(opt => opt.value !== 'computed').map(option => (
                                          <MenuItem key={option.value} value={option.value}>
                                            {option.label}
                                          </MenuItem>
                                        ))}
                                      </Select>
                                    </FormControl>
                                  )}
                                  <IconButton size="small" onClick={() => removeField('value-fields', index)}>
                                    <DeleteIcon fontSize="small" />
                                  </IconButton>
                                </Box>
                              )}
                            </Draggable>
                          ))}
                          {provided.placeholder}
                          {config.valueFields.length === 0 && (
                            <Typography variant="body2" color="text.secondary" textAlign="center">
                              将字段拖放到这里作为指标
                            </Typography>
                          )}
                        </Box>
                      )}
                    </Droppable>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>

            {/* 控制按钮 */}
            <Box mt={2} display="flex" gap={2}>
              <Button 
                variant="contained" 
                onClick={handleGeneratePivot}
                disabled={config.rowFields.length === 0 && config.colFields.length === 0}
              >
                生成透视表
              </Button>
              <Button 
                variant="outlined" 
                onClick={() => setConfig({ rowFields: [], colFields: [], valueFields: [], computedFields: [] })}
              >
                清除配置
              </Button>
            </Box>

            {/* 透视表预览 */}
            {generatePivotTable && (
              <Card sx={{ mt: 2 }}>
                <CardHeader title="透视表预览" />
                <CardContent>
                  <Typography variant="body2" color="text.secondary" gutterBottom>
                    数据行数: {data.length} | 
                    行字段: {config.rowFields.length} | 
                    列字段: {config.colFields.length} | 
                    指标: {config.valueFields.length} |
                    自定义字段: {config.computedFields.length}
                  </Typography>
                  <Typography variant="body2" sx={{ color: 'success.main' }}>
                    透视表配置完成，点击"生成透视表"查看结果
                  </Typography>
                </CardContent>
              </Card>
            )}
          </Grid>
        </Grid>

        {/* 自定义计算字段对话框 */}
        <Dialog open={computedDialogOpen} onClose={() => setComputedDialogOpen(false)} maxWidth="md" fullWidth>
          <DialogTitle>添加自定义计算字段</DialogTitle>
          <DialogContent>
            <Tabs value={activeComputedTab} onChange={(_, v) => setActiveComputedTab(v)} sx={{ mb: 2 }}>
              <Tab label="自定义公式" />
              <Tab label="常用模板" />
              <Tab label="运算帮助" />
            </Tabs>
            
            {activeComputedTab === 0 && (
              <Grid container spacing={2} sx={{ mt: 1 }}>
                <Grid item xs={12} md={6}>
                  <TextField
                    fullWidth
                    label="字段名称"
                    value={newComputedField.name}
                    onChange={(e) => setNewComputedField(prev => ({ ...prev, name: e.target.value }))}
                  />
                </Grid>
                <Grid item xs={12} md={6}>
                  <TextField
                    fullWidth
                    label="显示别名"
                    value={newComputedField.alias}
                    onChange={(e) => setNewComputedField(prev => ({ ...prev, alias: e.target.value }))}
                  />
                </Grid>
                <Grid item xs={12}>
                  <TextField
                    fullWidth
                    label="计算公式"
                    value={newComputedField.formula}
                    onChange={(e) => setNewComputedField(prev => ({ ...prev, formula: e.target.value }))}
                    placeholder="例如: clicks / views 或 orders + models"
                    multiline
                    rows={3}
                    helperText="支持 +, -, *, /, %, **, >, <, >=, <=, ==, != 运算符和 max, min, abs, round, pow 函数"
                  />
                </Grid>
                <Grid item xs={12} md={6}>
                  <FormControl fullWidth>
                    <InputLabel>数值格式</InputLabel>
                    <Select
                      value={newComputedField.format || 'decimal2'}
                      onChange={(e) => setNewComputedField(prev => ({ ...prev, format: e.target.value as FormatType }))}
                    >
                      {FORMAT_OPTIONS.map(option => (
                        <MenuItem key={option.value} value={option.value}>
                          {option.label} ({option.example})
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid>
                <Grid item xs={12}>
                  <Typography variant="body2" color="text.secondary">
                    可用字段: {availableFields.join(', ')}
                  </Typography>
                </Grid>
              </Grid>
            )}
            
            {activeComputedTab === 1 && (
              <Box sx={{ mt: 2 }}>
                {COMPUTED_FIELD_TEMPLATES.map((template, index) => (
                  <Card key={index} sx={{ mb: 2 }}>
                    <CardContent>
                      <Box display="flex" justifyContent="space-between" alignItems="center">
                        <Box>
                          <Typography variant="h6">{template.name}</Typography>
                          <Typography variant="body2" color="text.secondary">
                            {template.description}
                          </Typography>
                          <Typography variant="caption" color="primary">
                            公式: {template.formula}
                          </Typography>
                        </Box>
                        <Button 
                          variant="outlined" 
                          size="small" 
                          onClick={() => useComputedTemplate(template)}
                        >
                          使用模板
                        </Button>
                      </Box>
                    </CardContent>
                  </Card>
                ))}
              </Box>
            )}
            
            {activeComputedTab === 2 && (
              <Box sx={{ mt: 2 }}>
                <Typography variant="h6" gutterBottom>
                  支持的运算符和函数
                </Typography>
                
                <Card sx={{ mb: 2 }}>
                  <CardContent>
                    <Typography variant="subtitle2" gutterBottom>基础运算符</Typography>
                    <Typography variant="body2" component="div">
                      • <code>+</code> 加法：a + b<br/>
                      • <code>-</code> 减法：a - b<br/>
                      • <code>*</code> 乘法：a * b<br/>
                      • <code>/</code> 除法：a / b（自动处理除零）<br/>
                      • <code>%</code> 取模：a % b（自动处理除零）<br/>
                      • <code>**</code> 幂运算：a ** b<br/>
                    </Typography>
                  </CardContent>
                </Card>
                
                <Card sx={{ mb: 2 }}>
                  <CardContent>
                    <Typography variant="subtitle2" gutterBottom>逻辑运算符</Typography>
                    <Typography variant="body2" component="div">
                      • <code>&gt;</code> 大于：a &gt; b（返回 1 或 0）<br/>
                      • <code>&lt;</code> 小于：a &lt; b（返回 1 或 0）<br/>
                      • <code>&gt;=</code> 大于等于：a &gt;= b<br/>
                      • <code>&lt;=</code> 小于等于：a &lt;= b<br/>
                      • <code>==</code> 等于：a == b<br/>
                      • <code>!=</code> 不等于：a != b<br/>
                    </Typography>
                  </CardContent>
                </Card>
                
                <Card sx={{ mb: 2 }}>
                  <CardContent>
                    <Typography variant="subtitle2" gutterBottom>数学函数</Typography>
                    <Typography variant="body2" component="div">
                      • <code>abs(x)</code> 绝对值<br/>
                      • <code>max(a,b)</code> 最大值<br/>
                      • <code>min(a,b)</code> 最小值<br/>
                      • <code>round(x,位数)</code> 四舍五入<br/>
                      • <code>pow(a,b)</code> 幂运算（等同于a**b）<br/>
                    </Typography>
                  </CardContent>
                </Card>
                
                <Card>
                  <CardContent>
                    <Typography variant="subtitle2" gutterBottom>示例公式</Typography>
                    <Typography variant="body2" component="div">
                      • <code>clicks / views</code> - CTR计算<br/>
                      • <code>orders + models</code> - 总订单<br/>
                      • <code>(revenue - cost) / revenue</code> - 利润率<br/>
                      • <code>clicks &gt; 1000 ? 1 : 0</code> - 条件判断<br/>
                      • <code>max(clicks, views)</code> - 最大指标<br/>
                      • <code>round(cost / revenue * 100, 2)</code> - 成本占比（%）<br/>
                    </Typography>
                  </CardContent>
                </Card>
              </Box>
            )}
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setComputedDialogOpen(false)}>取消</Button>
            <Button onClick={addComputedField} variant="contained" disabled={activeComputedTab !== 0}>
              添加
            </Button>
          </DialogActions>
        </Dialog>

        {/* 保存配置对话框 */}
        <Dialog open={saveDialogOpen} onClose={() => setSaveDialogOpen(false)}>
          <DialogTitle>保存透视表配置</DialogTitle>
          <DialogContent>
            <TextField
              fullWidth
              label="配置名称"
              value={configName}
              onChange={(e) => setConfigName(e.target.value)}
              sx={{ mt: 1 }}
              placeholder="例如: 营收分析配置"
            />
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setSaveDialogOpen(false)}>取消</Button>
            <Button onClick={saveConfig} variant="contained" disabled={!configName}>
              保存
            </Button>
          </DialogActions>
        </Dialog>

        {/* 加载配置对话框 */}
        <Dialog open={loadDialogOpen} onClose={() => setLoadDialogOpen(false)} maxWidth="sm" fullWidth>
          <DialogTitle>加载透视表配置</DialogTitle>
          <DialogContent>
            <List>
              {savedConfigs.map((savedConfig, index) => (
                <ListItem key={index} divider>
                  <ListItemText
                    primary={savedConfig.name}
                    secondary={`行字段: ${savedConfig.rowFields?.length || 0}, 列字段: ${savedConfig.colFields?.length || 0}, 指标: ${savedConfig.valueFields?.length || 0}`}
                  />
                  <ListItemSecondaryAction>
                    <Button
                      variant="outlined"
                      size="small"
                      onClick={() => loadConfig(savedConfig)}
                    >
                      加载
                    </Button>
                  </ListItemSecondaryAction>
                </ListItem>
              ))}
            </List>
            {savedConfigs.length === 0 && (
              <Typography color="text.secondary" textAlign="center" py={3}>
                暂无保存的配置
              </Typography>
            )}
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setLoadDialogOpen(false)}>关闭</Button>
          </DialogActions>
        </Dialog>

        {/* 指标格式设置对话框 */}
        <Dialog open={formatDialogOpen} onClose={() => setFormatDialogOpen(false)} maxWidth="md" fullWidth>
          <DialogTitle>指标格式设置</DialogTitle>
          <DialogContent>
            <Typography variant="body2" color="text.secondary" gutterBottom>
              为每个指标字段设置显示格式
            </Typography>
            <Grid container spacing={2} sx={{ mt: 1 }}>
              {config.valueFields.map((field, index) => (
                <Grid item xs={12} md={6} key={field.field}>
                  <FormControl fullWidth>
                    <InputLabel>{field.field}</InputLabel>
                    <Select
                      value={field.format || 'number'}
                      onChange={(e) => {
                        const newValueFields = [...config.valueFields]
                        newValueFields[index] = { ...field, format: e.target.value as FormatType }
                        setConfig(prev => ({ ...prev, valueFields: newValueFields }))
                      }}
                    >
                      {FORMAT_OPTIONS.map(option => (
                        <MenuItem key={option.value} value={option.value}>
                          {option.label} ({option.example})
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid>
              ))}
              {config.computedFields.map((field, index) => (
                <Grid item xs={12} md={6} key={field.name}>
                  <FormControl fullWidth>
                    <InputLabel>{field.alias} (自定义)</InputLabel>
                    <Select
                      value={field.format || 'decimal2'}
                      onChange={(e) => {
                        const newComputedFields = [...config.computedFields]
                        newComputedFields[index] = { ...field, format: e.target.value as FormatType }
                        setConfig(prev => ({ ...prev, computedFields: newComputedFields }))
                      }}
                    >
                      {FORMAT_OPTIONS.map(option => (
                        <MenuItem key={option.value} value={option.value}>
                          {option.label} ({option.example})
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid>
              ))}
            </Grid>
            {config.valueFields.length === 0 && config.computedFields.length === 0 && (
              <Typography color="text.secondary" textAlign="center" py={3}>
                请先添加指标字段
              </Typography>
            )}
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setFormatDialogOpen(false)}>关闭</Button>
          </DialogActions>
        </Dialog>
      </Box>
    </DragDropContext>
  )
}