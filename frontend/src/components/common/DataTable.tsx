import React from 'react'
import {
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  TablePagination,
  Typography,
  Box,
  Chip,
} from '@mui/material'
import type { DataRow } from '@/types'

interface Column {
  key: string
  label: string
  width?: number | string
  align?: 'left' | 'right' | 'center' | 'inherit' | 'justify'
  format?: (value: unknown) => React.ReactNode
}

interface DataTableProps {
  data: DataRow[]
  columns?: Column[]
  title?: string
  maxHeight?: number | string
  pagination?: boolean
  pageSize?: number
  onRowClick?: (row: DataRow, index: number) => void
  emptyMessage?: string
}

export const DataTable: React.FC<DataTableProps> = ({
  data,
  columns,
  title,
  maxHeight = 400,
  pagination = true,
  pageSize = 25,
  onRowClick,
  emptyMessage = '暂无数据',
}) => {
  const [page, setPage] = React.useState(0)
  const [rowsPerPage, setRowsPerPage] = React.useState(pageSize)

  // Auto-generate columns from data if not provided
  const finalColumns = React.useMemo((): Column[] => {
    if (columns) return columns
    
    if (data.length === 0) return []
    
    const firstRow = data[0]
    return Object.keys(firstRow).map((key): Column => ({
      key,
      label: key,
      align: 'left',
    }))
  }, [columns, data])

  const handleChangePage = (_event: unknown, newPage: number): void => {
    setPage(newPage)
  }

  const handleChangeRowsPerPage = (event: React.ChangeEvent<HTMLInputElement>): void => {
    setRowsPerPage(parseInt(event.target.value, 10))
    setPage(0)
  }

  const paginatedData = pagination 
    ? data.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage)
    : data

  const formatValue = (value: unknown): React.ReactNode => {
    if (value === null || value === undefined) {
      return <Chip label="null" size="small" variant="outlined" />
    }
    
    if (typeof value === 'boolean') {
      return <Chip label={value.toString()} size="small" color={value ? 'success' : 'default'} />
    }
    
    if (typeof value === 'number') {
      return <Typography variant="body2" component="span" sx={{ fontFamily: 'monospace' }}>
        {value.toLocaleString()}
      </Typography>
    }
    
    if (typeof value === 'string' && value.length > 100) {
      return <Typography variant="body2" title={value}>
        {value.substring(0, 100)}...
      </Typography>
    }
    
    return String(value)
  }

  if (data.length === 0) {
    return (
      <Paper sx={{ p: 3, textAlign: 'center' }}>
        <Typography color="text.secondary">
          {emptyMessage}
        </Typography>
      </Paper>
    )
  }

  return (
    <Paper>
      {title && (
        <Box sx={{ p: 2, borderBottom: 1, borderColor: 'divider' }}>
          <Typography variant="h6">{title}</Typography>
          <Typography variant="body2" color="text.secondary">
            共 {data.length} 条记录
          </Typography>
        </Box>
      )}
      
      <TableContainer sx={{ maxHeight }}>
        <Table stickyHeader size="small">
          <TableHead>
            <TableRow>
              {finalColumns.map((column) => (
                <TableCell
                  key={column.key}
                  align={column.align || 'left'}
                  style={{ width: column.width || 'auto' }}
                  sx={{ fontWeight: 'bold' }}
                >
                  {column.label}
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {paginatedData.map((row, index) => (
              <TableRow
                key={index}
                hover={!!onRowClick}
                onClick={() => onRowClick?.(row, index)}
                sx={{ 
                  cursor: onRowClick ? 'pointer' : 'default',
                  '&:nth-of-type(odd)': { backgroundColor: 'action.hover' }
                }}
              >
                {finalColumns.map((column) => (
                  <TableCell key={column.key} align={column.align || 'left'}>
                    {column.format 
                      ? column.format(row[column.key])
                      : formatValue(row[column.key])
                    }
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
      
      {pagination && (
        <TablePagination
          rowsPerPageOptions={[10, 25, 50, 100]}
          component="div"
          count={data.length}
          rowsPerPage={rowsPerPage}
          page={page}
          onPageChange={handleChangePage}
          onRowsPerPageChange={handleChangeRowsPerPage}
          labelRowsPerPage="每页行数:"
          labelDisplayedRows={({ from, to, count }) => 
            `${from}-${to} 共 ${count !== -1 ? count : `超过 ${to}`} 条`
          }
        />
      )}
    </Paper>
  )
}