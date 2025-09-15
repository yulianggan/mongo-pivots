import React, { useState, useCallback, useRef } from 'react'
import {
  Box,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Typography,
  Chip,
  Button,
  Menu,
  MenuItem,
  IconButton
} from '@mui/material'
import {
  FileDownload as ExportIcon,
  GridOn as TableIcon
} from '@mui/icons-material'

// 数值格式类型
type FormatType = 'number' | 'currency' | 'percentage' | 'decimal1' | 'decimal2' | 'decimal3'

interface EnhancedPivotTableProps {
  pivotResult: {
    data: any
    colTotals: any
    grandTotal: any
    rowFields: string[]
    colFields: string[]
    valueFields: Array<{ 
      field: string
      aggregation?: string
      format?: FormatType
    }>
  } | null
}

export const EnhancedPivotTable: React.FC<EnhancedPivotTableProps> = ({ pivotResult }) => {
  const [hoveredRow, setHoveredRow] = useState<number | null>(null)
  const [hoveredCol, setHoveredCol] = useState<number | null>(null)
  const [columnWidths, setColumnWidths] = useState<Record<number, number>>({})
  const [exportAnchorEl, setExportAnchorEl] = useState<null | HTMLElement>(null)
  const tableRef = useRef<HTMLTableElement>(null)
  const resizingRef = useRef<{
    columnIndex: number
    startX: number
    startWidth: number
  } | null>(null)

  if (!pivotResult) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight={200}>
        <Typography color="text.secondary">
          请配置透视表字段并点击"生成透视表"
        </Typography>
      </Box>
    )
  }

  const { data, colTotals, grandTotal, rowFields, colFields, valueFields } = pivotResult

  // 获取所有行键和列键
  const rowKeys = Object.keys(data)
  const allColKeys = new Set<string>()
  
  Object.values(data).forEach((rowData: any) => {
    Object.keys(rowData).forEach(colKey => allColKeys.add(colKey))
  })
  
  const colKeys = Array.from(allColKeys)

  // 列宽调整相关函数
  const handleMouseDown = useCallback((e: React.MouseEvent, columnIndex: number) => {
    e.preventDefault()
    e.stopPropagation()
    
    const startX = e.clientX
    const currentWidth = columnWidths[columnIndex] || 120
    
    resizingRef.current = {
      columnIndex,
      startX,
      startWidth: currentWidth
    }

    const handleMouseMove = (e: MouseEvent) => {
      if (!resizingRef.current) return
      
      const deltaX = e.clientX - resizingRef.current.startX
      const newWidth = Math.max(80, resizingRef.current.startWidth + deltaX)
      
      setColumnWidths(prev => ({
        ...prev,
        [resizingRef.current!.columnIndex]: newWidth
      }))
    }

    const handleMouseUp = () => {
      resizingRef.current = null
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }

    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
  }, [columnWidths])

  // 导出功能
  const exportToCSV = useCallback(() => {
    const csvRows: string[] = []
    
    // 构建标题行
    const headers = [
      ...rowFields,
      ...colKeys.length === 0 
        ? valueFields.map(v => `${v.field} (${v.aggregation || 'sum'})`)
        : colKeys.flatMap(colKey => 
            valueFields.map(v => `${parseKey(colKey, colFields)} - ${v.field} (${v.aggregation || 'sum'})`)
          )
    ]
    csvRows.push(headers.join(','))
    
    // 构建数据行
    rowKeys.forEach(rowKey => {
      const row = [
        ...parseKey(rowKey, rowFields).split(' | ').map(part => 
          `"${(part.split(': ')[1] || part).replace(/"/g, '""')}"`
        ),
        ...colKeys.length === 0 
          ? valueFields.map(v => data[rowKey]?.['']?.[v.field] || 0)
          : colKeys.flatMap(colKey => 
              valueFields.map(v => data[rowKey]?.[colKey]?.[v.field] || 0)
            )
      ]
      csvRows.push(row.join(','))
    })
    
    // 添加汇总行
    if (colKeys.length > 0) {
      const summaryRow = [
        '汇总',
        ...Array(rowFields.length - 1).fill(''),
        ...colKeys.flatMap(colKey => 
          valueFields.map(v => colTotals[colKey]?.[v.field] || 0)
        )
      ]
      csvRows.push(summaryRow.join(','))
    } else if (rowKeys.length > 1) {
      const grandTotalRow = [
        '总计',
        ...Array(rowFields.length - 1).fill(''),
        ...valueFields.map(v => grandTotal[v.field] || 0)
      ]
      csvRows.push(grandTotalRow.join(','))
    }
    
    const csvContent = csvRows.join('\n')
    const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' })
    const link = document.createElement('a')
    const url = URL.createObjectURL(blob)
    link.setAttribute('href', url)
    link.setAttribute('download', `pivot_table_${new Date().toISOString().slice(0, 10)}.csv`)
    link.style.visibility = 'hidden'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    setExportAnchorEl(null)
  }, [data, colTotals, grandTotal, rowKeys, colKeys, rowFields, colFields, valueFields])

  const exportToExcel = useCallback(() => {
    // 创建表格HTML用于Excel导出
    const tableHTML = `
      <table>
        <thead>
          <tr>
            ${rowFields.map(field => `<th>${field}</th>`).join('')}
            ${colKeys.length === 0 
              ? valueFields.map(v => `<th>${v.field} (${v.aggregation || 'sum'})</th>`).join('')
              : colKeys.flatMap(colKey => 
                  valueFields.map(v => `<th>${parseKey(colKey, colFields)} - ${v.field} (${v.aggregation || 'sum'})</th>`)
                ).join('')
            }
          </tr>
        </thead>
        <tbody>
          ${rowKeys.map(rowKey => `
            <tr>
              ${parseKey(rowKey, rowFields).split(' | ').map(part => 
                `<td>${part.split(': ')[1] || part}</td>`
              ).join('')}
              ${colKeys.length === 0 
                ? valueFields.map(v => `<td>${data[rowKey]?.['']?.[v.field] || 0}</td>`).join('')
                : colKeys.flatMap(colKey => 
                    valueFields.map(v => `<td>${data[rowKey]?.[colKey]?.[v.field] || 0}</td>`)
                  ).join('')
              }
            </tr>
          `).join('')}
          ${colKeys.length > 0 ? `
            <tr>
              <td>汇总</td>
              ${Array(rowFields.length - 1).fill('<td></td>').join('')}
              ${colKeys.flatMap(colKey => 
                valueFields.map(v => `<td>${colTotals[colKey]?.[v.field] || 0}</td>`)
              ).join('')}
            </tr>
          ` : ''}
          ${colKeys.length === 0 && rowKeys.length > 1 ? `
            <tr>
              <td>总计</td>
              ${Array(rowFields.length - 1).fill('<td></td>').join('')}
              ${valueFields.map(v => `<td>${grandTotal[v.field] || 0}</td>`).join('')}
            </tr>
          ` : ''}
        </tbody>
      </table>
    `
    
    const blob = new Blob([tableHTML], { type: 'application/vnd.ms-excel' })
    const link = document.createElement('a')
    const url = URL.createObjectURL(blob)
    link.setAttribute('href', url)
    link.setAttribute('download', `pivot_table_${new Date().toISOString().slice(0, 10)}.xls`)
    link.style.visibility = 'hidden'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    setExportAnchorEl(null)
  }, [data, colTotals, grandTotal, rowKeys, colKeys, rowFields, colFields, valueFields])

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

  // 解析行/列键为显示标签
  const parseKey = (key: string, fields: string[]): string => {
    if (key === 'null' || !key) return '(空)'
    const values = key.split('|')
    return values.map((val, idx) => 
      `${fields[idx] || 'field'}: ${val === 'null' ? '(空)' : val}`
    ).join(' | ')
  }

  // 计算总列数
  const totalColumns = rowFields.length + (colKeys.length === 0 ? valueFields.length : colKeys.length * valueFields.length)

  return (
    <Box>
      {/* 工具栏 */}
      <Box mb={2} display="flex" justifyContent="space-between" alignItems="center">
        {/* 配置信息 */}
        <Box display="flex" flexWrap="wrap" gap={1}>
          {rowFields.length > 0 && (
            <Chip 
              label={`行: ${rowFields.join(', ')}`} 
              color="primary" 
              variant="outlined" 
              size="small" 
            />
          )}
          {colFields.length > 0 && (
            <Chip 
              label={`列: ${colFields.join(', ')}`} 
              color="secondary" 
              variant="outlined" 
              size="small" 
            />
          )}
          {valueFields.length > 0 && (
            <Chip 
              label={`指标: ${valueFields.map(v => `${v.field}(${v.aggregation || 'sum'})`).join(', ')}`} 
              color="success" 
              variant="outlined" 
              size="small" 
            />
          )}
        </Box>

        {/* 导出按钮 */}
        <Box>
          <Button
            variant="outlined"
            startIcon={<ExportIcon />}
            onClick={(e) => setExportAnchorEl(e.currentTarget)}
            size="small"
          >
            导出数据
          </Button>
          <Menu
            anchorEl={exportAnchorEl}
            open={Boolean(exportAnchorEl)}
            onClose={() => setExportAnchorEl(null)}
          >
            <MenuItem onClick={exportToCSV}>导出为 CSV</MenuItem>
            <MenuItem onClick={exportToExcel}>导出为 Excel</MenuItem>
          </Menu>
        </Box>
      </Box>

      {/* 透视表 */}
      <Box sx={{ position: 'relative' }}>
        <TableContainer 
          component={Paper} 
          sx={{ 
            maxHeight: 600, 
            overflowY: 'auto',
            border: '1px solid',
            borderColor: 'divider'
          }}
        >
          <Table ref={tableRef} stickyHeader size="small" sx={{ tableLayout: 'fixed' }}>
            <TableHead>
              <TableRow>
                {/* 行字段标题 */}
                {rowFields.map((field, idx) => (
                  <TableCell 
                    key={field} 
                    sx={{ 
                      fontWeight: 'bold', 
                      bgcolor: 'grey.100',
                      width: columnWidths[idx] || 120,
                      minWidth: 80,
                      position: 'sticky',
                      left: idx === 0 ? 0 : `${Object.entries(columnWidths).slice(0, idx).reduce((sum, [, width]) => sum + width, 0) + (idx - Object.keys(columnWidths).filter(k => parseInt(k) < idx).length) * 120}px`,
                      zIndex: 3,
                      borderRight: '2px solid white',
                      background: hoveredCol === idx ? 'rgba(33, 150, 243, 0.08)' : 'grey.100'
                    }}
                    onMouseEnter={() => setHoveredCol(idx)}
                    onMouseLeave={() => setHoveredCol(null)}
                  >
                    <Box sx={{ 
                      display: 'flex', 
                      justifyContent: 'space-between', 
                      alignItems: 'center',
                      pr: 1
                    }}>
                      <Typography variant="body2" noWrap>{field}</Typography>
                      <Box
                        sx={{
                          width: '4px',
                          height: '20px',
                          cursor: 'col-resize',
                          bgcolor: 'primary.main',
                          opacity: 0.3,
                          '&:hover': { opacity: 0.8 }
                        }}
                        onMouseDown={(e) => handleMouseDown(e, idx)}
                      />
                    </Box>
                  </TableCell>
                ))}
                
                {/* 列字段标题 + 指标 */}
                {colKeys.length === 0 ? (
                  valueFields.map((valueField, idx) => {
                    const colIndex = rowFields.length + idx
                    return (
                      <TableCell 
                        key={valueField.field} 
                        align="right" 
                        sx={{ 
                          fontWeight: 'bold', 
                          bgcolor: 'grey.100',
                          width: columnWidths[colIndex] || 120,
                          minWidth: 80,
                          background: hoveredCol === colIndex ? 'rgba(33, 150, 243, 0.08)' : 'grey.100'
                        }}
                        onMouseEnter={() => setHoveredCol(colIndex)}
                        onMouseLeave={() => setHoveredCol(null)}
                      >
                        <Box sx={{ 
                          display: 'flex', 
                          justifyContent: 'space-between', 
                          alignItems: 'center',
                          pr: 1
                        }}>
                          <Typography variant="body2" noWrap>
                            {valueField.field} ({valueField.aggregation || 'sum'})
                          </Typography>
                          <Box
                            sx={{
                              width: '4px',
                              height: '20px',
                              cursor: 'col-resize',
                              bgcolor: 'primary.main',
                              opacity: 0.3,
                              '&:hover': { opacity: 0.8 }
                            }}
                            onMouseDown={(e) => handleMouseDown(e, colIndex)}
                          />
                        </Box>
                      </TableCell>
                    )
                  })
                ) : (
                  colKeys.flatMap((colKey, colIdx) => 
                    valueFields.map((valueField, valIdx) => {
                      const colIndex = rowFields.length + colIdx * valueFields.length + valIdx
                      return (
                        <TableCell 
                          key={`${colKey}-${valueField.field}`} 
                          align="right" 
                          sx={{ 
                            fontWeight: 'bold', 
                            bgcolor: 'grey.100',
                            width: columnWidths[colIndex] || 120,
                            minWidth: 80,
                            background: hoveredCol === colIndex ? 'rgba(33, 150, 243, 0.08)' : 'grey.100'
                          }}
                          onMouseEnter={() => setHoveredCol(colIndex)}
                          onMouseLeave={() => setHoveredCol(null)}
                        >
                          <Box sx={{ 
                            display: 'flex', 
                            justifyContent: 'space-between', 
                            alignItems: 'center',
                            pr: 1
                          }}>
                            <Box sx={{ flexGrow: 1, mr: 1 }}>
                              <Typography variant="caption" display="block" noWrap>
                                {parseKey(colKey, colFields)}
                              </Typography>
                              <Typography variant="body2" noWrap>
                                {valueField.field} ({valueField.aggregation || 'sum'})
                              </Typography>
                            </Box>
                            <Box
                              sx={{
                                width: '4px',
                                height: '20px',
                                cursor: 'col-resize',
                                bgcolor: 'primary.main',
                                opacity: 0.3,
                                '&:hover': { opacity: 0.8 }
                              }}
                              onMouseDown={(e) => handleMouseDown(e, colIndex)}
                            />
                          </Box>
                        </TableCell>
                      )
                    })
                  )
                )}
              </TableRow>
            </TableHead>
            
            <TableBody>
              {rowKeys.map((rowKey, rowIdx) => (
                <TableRow 
                  key={rowKey} 
                  sx={{
                    '&:hover': { bgcolor: 'action.hover' },
                    bgcolor: hoveredRow === rowIdx ? 'rgba(33, 150, 243, 0.04)' : 'inherit'
                  }}
                  onMouseEnter={() => setHoveredRow(rowIdx)}
                  onMouseLeave={() => setHoveredRow(null)}
                >
                  {/* 行字段值 */}
                  {parseKey(rowKey, rowFields).split(' | ').map((part, idx) => (
                    <TableCell 
                      key={idx} 
                      sx={{ 
                        fontWeight: 'medium',
                        width: columnWidths[idx] || 120,
                        minWidth: 80,
                        position: idx < rowFields.length ? 'sticky' : 'static',
                        left: idx === 0 ? 0 : `${Object.entries(columnWidths).slice(0, idx).reduce((sum, [, width]) => sum + width, 0) + (idx - Object.keys(columnWidths).filter(k => parseInt(k) < idx).length) * 120}px`,
                        zIndex: idx < rowFields.length ? 2 : 'auto',
                        bgcolor: idx < rowFields.length ? 'background.paper' : 'inherit',
                        borderRight: idx < rowFields.length ? '1px solid' : 'none',
                        borderRightColor: 'divider',
                        background: (hoveredRow === rowIdx || hoveredCol === idx) ? 
                          'rgba(33, 150, 243, 0.08)' : 
                          (idx < rowFields.length ? 'background.paper' : 'inherit')
                      }}
                    >
                      <Typography variant="body2" noWrap>
                        {part.split(': ')[1] || part}
                      </Typography>
                    </TableCell>
                  ))}
                  
                  {/* 数据单元格 */}
                  {colKeys.length === 0 ? (
                    valueFields.map((valueField, idx) => {
                      const colIndex = rowFields.length + idx
                      return (
                        <TableCell 
                          key={valueField.field} 
                          align="right"
                          sx={{
                            width: columnWidths[colIndex] || 120,
                            minWidth: 80,
                            background: (hoveredRow === rowIdx || hoveredCol === colIndex) ? 
                              'rgba(33, 150, 243, 0.08)' : 'inherit'
                          }}
                        >
                          <Typography variant="body2" noWrap>
                            {formatValue(
                              data[rowKey]?.['']?.[valueField.field] || 0, 
                              valueField.format || 'number'
                            )}
                          </Typography>
                        </TableCell>
                      )
                    })
                  ) : (
                    colKeys.flatMap((colKey, colIdx) => 
                      valueFields.map((valueField, valIdx) => {
                        const colIndex = rowFields.length + colIdx * valueFields.length + valIdx
                        return (
                          <TableCell 
                            key={`${colKey}-${valueField.field}`} 
                            align="right"
                            sx={{
                              width: columnWidths[colIndex] || 120,
                              minWidth: 80,
                              background: (hoveredRow === rowIdx || hoveredCol === colIndex) ? 
                                'rgba(33, 150, 243, 0.08)' : 'inherit'
                            }}
                          >
                            <Typography variant="body2" noWrap>
                              {formatValue(
                                data[rowKey]?.[colKey]?.[valueField.field] || 0, 
                                valueField.format || 'number'
                              )}
                            </Typography>
                          </TableCell>
                        )
                      })
                    )
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>

        {/* 固定在底部的汇总行 */}
        {(colKeys.length > 0 || (colKeys.length === 0 && rowKeys.length > 1)) && (
          <Paper 
            sx={{ 
              position: 'sticky', 
              bottom: 0, 
              zIndex: 4,
              mt: 1,
              border: '2px solid',
              borderColor: 'primary.main',
              borderRadius: 1
            }}
          >
            <Table size="small" sx={{ tableLayout: 'fixed' }}>
              <TableBody>
                {colKeys.length > 0 ? (
                  <TableRow sx={{ bgcolor: 'warning.light' }}>
                    {rowFields.map((_, idx) => (
                      <TableCell 
                        key={idx} 
                        sx={{ 
                          fontWeight: 'bold',
                          width: columnWidths[idx] || 120,
                          minWidth: 80
                        }}
                      >
                        {idx === 0 ? '汇总' : ''}
                      </TableCell>
                    ))}
                    
                    {colKeys.flatMap((colKey, colIdx) => 
                      valueFields.map((valueField, valIdx) => {
                        const colIndex = rowFields.length + colIdx * valueFields.length + valIdx
                        return (
                          <TableCell 
                            key={`col-total-${colKey}-${valueField.field}`} 
                            align="right" 
                            sx={{ 
                              fontWeight: 'bold',
                              width: columnWidths[colIndex] || 120,
                              minWidth: 80
                            }}
                          >
                            {formatValue(
                              colTotals[colKey]?.[valueField.field] || 0, 
                              valueField.format || 'number'
                            )}
                          </TableCell>
                        )
                      })
                    )}
                  </TableRow>
                ) : (
                  <TableRow sx={{ bgcolor: 'error.light' }}>
                    {rowFields.map((_, idx) => (
                      <TableCell 
                        key={idx} 
                        sx={{ 
                          fontWeight: 'bold',
                          width: columnWidths[idx] || 120,
                          minWidth: 80
                        }}
                      >
                        {idx === 0 ? '总计' : ''}
                      </TableCell>
                    ))}
                    {valueFields.map((valueField, idx) => {
                      const colIndex = rowFields.length + idx
                      return (
                        <TableCell 
                          key={`grand-${valueField.field}`} 
                          align="right" 
                          sx={{ 
                            fontWeight: 'bold',
                            width: columnWidths[colIndex] || 120,
                            minWidth: 80
                          }}
                        >
                          {formatValue(
                            grandTotal[valueField.field] || 0, 
                            valueField.format || 'number'
                          )}
                        </TableCell>
                      )
                    })}
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </Paper>
        )}
      </Box>
      
      {/* 统计信息 */}
      <Box mt={2} display="flex" justifyContent="space-between" alignItems="center">
        <Typography variant="body2" color="text.secondary">
          行数: {rowKeys.length} | 列数: {Math.max(colKeys.length, 1)} | 指标数: {valueFields.length}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          数据源: {Object.keys(data).reduce((sum, rowKey) => 
            sum + Object.keys(data[rowKey]).length, 0
          )} 个数据点
        </Typography>
      </Box>
    </Box>
  )
}