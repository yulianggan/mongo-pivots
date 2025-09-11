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
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Divider
} from '@mui/material'
import {
  Delete as DeleteIcon,
  Add as AddIcon,
  Settings as SettingsIcon,
  Calculate as CalculateIcon
} from '@mui/icons-material'
import { DragDropContext, Droppable, Draggable, DropResult } from 'react-beautiful-dnd'

// 聚合方式类型
type AggregationType = 'sum' | 'avg' | 'count' | 'max' | 'min' | 'first' | 'last'

// 字段配置接口
interface FieldConfig {
  field: string
  aggregation?: AggregationType
  alias?: string
}

// 自定义计算字段
interface ComputedField {
  name: string
  formula: string
  alias: string
}

// 透视表配置
interface PivotConfig {
  rowFields: FieldConfig[]
  colFields: FieldConfig[]
  valueFields: FieldConfig[]
  computedFields: ComputedField[]
}

interface DragDropPivotLayoutProps {
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
  { value: 'last', label: '最后一个' }
]

export const DragDropPivotLayout: React.FC<DragDropPivotLayoutProps> = ({
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
  const [newComputedField, setNewComputedField] = useState<ComputedField>({
    name: '',
    formula: '',
    alias: ''
  })

  // 处理拖拽结果
  const onDragEnd = (result: DropResult) => {
    const { source, destination } = result

    if (!destination) return

    // 从可用字段拖拽到配置区域
    if (source.droppableId === 'available-fields') {
      const fieldName = availableFields[source.index]
      const newField: FieldConfig = {
        field: fieldName,
        aggregation: destination.droppableId === 'value-fields' ? 'sum' : undefined
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

  // 计算自定义字段值
  const calculateComputedValue = (formula: string, row: any): number => {
    try {
      // 简单的公式解析和计算
      let expression = formula
      
      // 替换字段名为实际值
      Object.keys(row).forEach(field => {
        const regex = new RegExp(`\\b${field}\\b`, 'g')
        expression = expression.replace(regex, String(row[field] || 0))
      })

      // 处理除法，确保分母不为0
      expression = expression.replace(/(\d+\.?\d*)\s*\/\s*(\d+\.?\d*)/g, (match, a, b) => {
        return String(safeDivide(parseFloat(a), parseFloat(b)))
      })

      // 使用Function构造器安全计算
      const result = new Function('return ' + expression)()
      return isNaN(result) ? 0 : result
    } catch (error) {
      console.warn('计算公式错误:', error)
      return 0
    }
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
    const valueFieldConfigs = config.valueFields

    if (rowFieldNames.length === 0 && colFieldNames.length === 0) {
      return null
    }

    // 基本的透视表数据结构
    const pivotData: any = {}
    const rowTotals: any = {}
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
        rowTotals[rowKey] = {}
        valueFieldConfigs.forEach(valueField => {
          rowTotals[rowKey][valueField.field] = 0
        })
      }

      if (!pivotData[rowKey][colKey]) {
        pivotData[rowKey][colKey] = {}
        valueFieldConfigs.forEach(valueField => {
          pivotData[rowKey][colKey][valueField.field] = 0
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
        const value = parseFloat(row[valueField.field]) || 0
        const aggregation = valueField.aggregation || 'sum'

        switch (aggregation) {
          case 'sum':
            pivotData[rowKey][colKey][valueField.field] += value
            rowTotals[rowKey][valueField.field] += value
            colTotals[colKey][valueField.field] += value
            grandTotal[valueField.field] += value
            break
          case 'count':
            pivotData[rowKey][colKey][valueField.field] += 1
            rowTotals[rowKey][valueField.field] += 1
            colTotals[colKey][valueField.field] += 1
            grandTotal[valueField.field] += 1
            break
          // TODO: 实现其他聚合方式
          default:
            pivotData[rowKey][colKey][valueField.field] += value
        }
      })
    })

    return {
      data: pivotData,
      rowTotals,
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

    setNewComputedField({ name: '', formula: '', alias: '' })
    setComputedDialogOpen(false)
  }

  // 生成透视表
  const handleGeneratePivot = () => {
    const result = generatePivotTable
    onPivotUpdate(result)
  }

  return (
    <DragDropContext onDragEnd={onDragEnd}>
      <Box>
        <Grid container spacing={3}>
          {/* 可用字段 */}
          <Grid item xs={12} md={3}>
            <Card>
              <CardHeader 
                title="可用字段" 
                action={
                  <IconButton onClick={() => setComputedDialogOpen(true)}>
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
                      {availableFields.map((field, index) => (
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
                                  <FormControl size="small" sx={{ minWidth: 80 }}>
                                    <Select
                                      value={fieldConfig.aggregation || 'sum'}
                                      onChange={(e) => updateAggregation('value-fields', index, e.target.value as AggregationType)}
                                      size="small"
                                    >
                                      {AGGREGATION_OPTIONS.map(option => (
                                        <MenuItem key={option.value} value={option.value}>
                                          {option.label}
                                        </MenuItem>
                                      ))}
                                    </Select>
                                  </FormControl>
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
                    指标: {config.valueFields.length}
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
                  placeholder="例如: 总销售额 / 总成本 * 100 (支持 +、-、*、/ 运算，分母为0时自动返回0)"
                  multiline
                  rows={3}
                />
              </Grid>
              <Grid item xs={12}>
                <Typography variant="body2" color="text.secondary">
                  可用字段: {availableFields.join(', ')}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  注意: 除法运算会自动处理分母为0的情况，返回0而不是错误
                </Typography>
              </Grid>
            </Grid>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setComputedDialogOpen(false)}>取消</Button>
            <Button onClick={addComputedField} variant="contained">添加</Button>
          </DialogActions>
        </Dialog>
      </Box>
    </DragDropContext>
  )
}