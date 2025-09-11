import React from 'react'
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
  Chip
} from '@mui/material'

interface PivotTableProps {
  pivotResult: {
    data: any
    rowTotals: any
    colTotals: any
    grandTotal: any
    rowFields: string[]
    colFields: string[]
    valueFields: Array<{ field: string; aggregation?: string }>
  } | null
}

export const PivotTable: React.FC<PivotTableProps> = ({ pivotResult }) => {
  if (!pivotResult) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight={200}>
        <Typography color="text.secondary">
          请配置透视表字段并点击"生成透视表"
        </Typography>
      </Box>
    )
  }

  const { data, rowTotals, colTotals, grandTotal, rowFields, colFields, valueFields } = pivotResult

  // 获取所有行键和列键
  const rowKeys = Object.keys(data)
  const allColKeys = new Set<string>()
  
  Object.values(data).forEach((rowData: any) => {
    Object.keys(rowData).forEach(colKey => allColKeys.add(colKey))
  })
  
  const colKeys = Array.from(allColKeys)

  // 格式化数值
  const formatValue = (value: number, aggregation?: string): string => {
    if (value === null || value === undefined || isNaN(value)) return '0'
    
    switch (aggregation) {
      case 'avg':
        return value.toFixed(2)
      case 'count':
        return Math.round(value).toString()
      default:
        return typeof value === 'number' ? value.toLocaleString() : String(value)
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

  return (
    <Box>
      {/* 配置信息 */}
      <Box mb={2} display="flex" flexWrap="wrap" gap={1}>
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

      {/* 透视表 */}
      <TableContainer component={Paper} sx={{ maxHeight: 600, overflowY: 'auto' }}>
        <Table stickyHeader size="small">
          <TableHead>
            <TableRow>
              {/* 行字段标题 */}
              {rowFields.map(field => (
                <TableCell key={field} sx={{ fontWeight: 'bold', bgcolor: 'grey.100' }}>
                  {field}
                </TableCell>
              ))}
              
              {/* 列字段标题 + 指标 */}
              {colKeys.length === 0 ? (
                valueFields.map(valueField => (
                  <TableCell key={valueField.field} align="right" sx={{ fontWeight: 'bold', bgcolor: 'grey.100' }}>
                    {valueField.field} ({valueField.aggregation || 'sum'})
                  </TableCell>
                ))
              ) : (
                colKeys.map(colKey => 
                  valueFields.map(valueField => (
                    <TableCell 
                      key={`${colKey}-${valueField.field}`} 
                      align="right" 
                      sx={{ fontWeight: 'bold', bgcolor: 'grey.100' }}
                    >
                      <Box>
                        <Typography variant="caption" display="block">
                          {parseKey(colKey, colFields)}
                        </Typography>
                        <Typography variant="body2">
                          {valueField.field} ({valueField.aggregation || 'sum'})
                        </Typography>
                      </Box>
                    </TableCell>
                  ))
                )
              )}
            </TableRow>
          </TableHead>
          
          <TableBody>
            {rowKeys.map(rowKey => (
              <TableRow key={rowKey} hover>
                {/* 行字段值 */}
                {parseKey(rowKey, rowFields).split(' | ').map((part, idx) => (
                  <TableCell key={idx} sx={{ fontWeight: 'medium' }}>
                    {part.split(': ')[1] || part}
                  </TableCell>
                ))}
                
                {/* 数据单元格 */}
                {colKeys.length === 0 ? (
                  valueFields.map(valueField => (
                    <TableCell key={valueField.field} align="right">
                      {formatValue(
                        data[rowKey]?.['']?.[valueField.field] || 0, 
                        valueField.aggregation
                      )}
                    </TableCell>
                  ))
                ) : (
                  colKeys.map(colKey => 
                    valueFields.map(valueField => (
                      <TableCell key={`${colKey}-${valueField.field}`} align="right">
                        {formatValue(
                          data[rowKey]?.[colKey]?.[valueField.field] || 0, 
                          valueField.aggregation
                        )}
                      </TableCell>
                    ))
                  )
                )}
              </TableRow>
            ))}
            
            {/* 列汇总行 */}
            {colKeys.length > 0 && (
              <TableRow sx={{ bgcolor: 'warning.light' }}>
                {rowFields.map((_, idx) => (
                  <TableCell key={idx} sx={{ fontWeight: 'bold' }}>
                    {idx === 0 ? '列汇总' : ''}
                  </TableCell>
                ))}
                
                {colKeys.map(colKey => 
                  valueFields.map(valueField => (
                    <TableCell 
                      key={`col-total-${colKey}-${valueField.field}`} 
                      align="right" 
                      sx={{ fontWeight: 'bold' }}
                    >
                      {formatValue(colTotals[colKey]?.[valueField.field] || 0, valueField.aggregation)}
                    </TableCell>
                  ))
                )}
              </TableRow>
            )}
            
            {/* 总计行（当没有列字段时） */}
            {colKeys.length === 0 && rowKeys.length > 1 && (
              <TableRow sx={{ bgcolor: 'error.light' }}>
                {rowFields.map((_, idx) => (
                  <TableCell key={idx} sx={{ fontWeight: 'bold' }}>
                    {idx === 0 ? '总计' : ''}
                  </TableCell>
                ))}
                {valueFields.map(valueField => (
                  <TableCell 
                    key={`grand-${valueField.field}`} 
                    align="right" 
                    sx={{ fontWeight: 'bold' }}
                  >
                    {formatValue(grandTotal[valueField.field] || 0, valueField.aggregation)}
                  </TableCell>
                ))}
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      
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