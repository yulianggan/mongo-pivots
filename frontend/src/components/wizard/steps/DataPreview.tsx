import React, { useEffect } from 'react'
import {
  Box,
  Typography,
  Grid,
  Card,
  CardHeader,
  CardContent,
} from '@mui/material'
import { DataTable } from '@/components/common'

interface DataPreviewProps {
  dataSources: any[]
  previewData: Record<string, any[]>
  onUpdate: (previewData: Record<string, any[]>) => void
}

export const DataPreview: React.FC<DataPreviewProps> = ({
  dataSources,
  previewData,
  onUpdate,
}) => {
  useEffect(() => {
    // Generate mock preview data for selected sources
    const mockPreviewData: Record<string, any[]> = {}
    
    dataSources.forEach(source => {
      if (source.id === 'customers') {
        mockPreviewData[source.id] = [
          { customer_id: 'C001', name: '张三', email: 'zhangsan@example.com', city: '北京', created_at: '2023-01-15' },
          { customer_id: 'C002', name: '李四', email: 'lisi@example.com', city: '上海', created_at: '2023-01-16' },
          { customer_id: 'C003', name: '王五', email: 'wangwu@example.com', city: '广州', created_at: '2023-01-17' },
        ]
      } else if (source.id === 'orders') {
        mockPreviewData[source.id] = [
          { order_id: 'O001', customer_id: 'C001', amount: 299.99, status: 'completed', order_date: '2023-03-15' },
          { order_id: 'O002', customer_id: 'C002', amount: 159.50, status: 'pending', order_date: '2023-03-16' },
          { order_id: 'O003', customer_id: 'C001', amount: 89.99, status: 'completed', order_date: '2023-03-17' },
        ]
      } else {
        mockPreviewData[source.id] = [
          { id: 1, field1: 'value1', field2: 'value2', field3: 100 },
          { id: 2, field1: 'value3', field2: 'value4', field3: 200 },
        ]
      }
    })
    
    onUpdate(mockPreviewData)
  }, [dataSources, onUpdate])

  if (dataSources.length === 0) {
    return (
      <Box textAlign="center" py={4}>
        <Typography variant="body1" color="text.secondary">
          请先选择数据源
        </Typography>
      </Box>
    )
  }

  return (
    <Box>
      <Typography variant="h6" gutterBottom>
        数据预览
      </Typography>
      
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        查看所选数据源的字段结构和样本数据，确认数据格式正确。
      </Typography>

      <Grid container spacing={2}>
        {dataSources.map((source, index) => (
          <Grid item xs={12} key={source.id}>
            <Card>
              <CardHeader
                title={source.name}
                subheader={`${source.records.toLocaleString()} 条记录 | ${source.fields.length} 个字段`}
              />
              <CardContent>
                {previewData[source.id] && (
                  <DataTable
                    data={previewData[source.id]}
                    title={`预览数据 (前3行)`}
                    maxHeight={300}
                    pagination={false}
                  />
                )}
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>
    </Box>
  )
}