import React, { useState } from 'react'
import {
  Box,
  Typography,
  Grid,
  Card,
  CardContent,
  CardActions,
  Button,
  Chip,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  ListItemSecondaryAction,
  Checkbox,
  Alert,
} from '@mui/material'
import {
  InsertDriveFile as FileIcon,
  Storage as DatabaseIcon,
  CheckCircle as CheckIcon,
  Add as AddIcon,
} from '@mui/icons-material'

interface DataSourceSelectionProps {
  dataSources: any[]
  onUpdate: (dataSources: any[]) => void
}

// Mock data sources
const mockDataSources = [
  {
    id: 'customers',
    name: 'customers.csv',
    type: 'file',
    format: 'csv',
    size: '2.3 MB',
    records: 1520,
    fields: ['customer_id', 'name', 'email', 'city', 'created_at'],
    status: 'ready',
  },
  {
    id: 'orders', 
    name: 'orders.xlsx',
    type: 'file',
    format: 'excel',
    size: '5.8 MB', 
    records: 8942,
    fields: ['order_id', 'customer_id', 'amount', 'status', 'order_date'],
    status: 'ready',
  },
  {
    id: 'products',
    name: 'products.json',
    type: 'file', 
    format: 'json',
    size: '1.1 MB',
    records: 856,
    fields: ['product_id', 'name', 'category', 'price', 'stock'],
    status: 'ready',
  },
  {
    id: 'mongo_sales',
    name: 'sales',
    type: 'database',
    format: 'mongodb',
    size: '12.3 MB',
    records: 25680,
    fields: ['_id', 'date', 'product', 'quantity', 'revenue'],
    status: 'ready',
  },
]

export const DataSourceSelection: React.FC<DataSourceSelectionProps> = ({
  dataSources,
  onUpdate,
}) => {
  const [selectedSources, setSelectedSources] = useState<string[]>(
    dataSources.map(ds => ds.id) || []
  )

  const handleSelectionChange = (sourceId: string, selected: boolean): void => {
    let newSelection: string[]
    
    if (selected) {
      newSelection = [...selectedSources, sourceId]
    } else {
      newSelection = selectedSources.filter(id => id !== sourceId)
    }
    
    setSelectedSources(newSelection)
    
    // Update parent component
    const selectedDataSources = mockDataSources.filter(ds => 
      newSelection.includes(ds.id)
    )
    onUpdate(selectedDataSources)
  }

  const getSourceIcon = (type: string, format: string) => {
    if (type === 'database') return <DatabaseIcon color="primary" />
    return <FileIcon color="secondary" />
  }

  const getFormatColor = (format: string): 'default' | 'primary' | 'secondary' | 'error' | 'info' | 'success' | 'warning' => {
    switch (format) {
      case 'csv': return 'success'
      case 'excel': return 'info' 
      case 'json': return 'warning'
      case 'mongodb': return 'primary'
      default: return 'default'
    }
  }

  return (
    <Box>
      <Typography variant="h6" gutterBottom>
        选择要连接的数据源
      </Typography>
      
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        选择至少2个数据源进行连接操作。可以混合选择文件和数据库数据源。
      </Typography>

      {selectedSources.length < 2 && (
        <Alert severity="info" sx={{ mb: 3 }}>
          请至少选择2个数据源才能继续下一步
        </Alert>
      )}

      <Grid container spacing={2}>
        {mockDataSources.map((source) => {
          const isSelected = selectedSources.includes(source.id)
          
          return (
            <Grid item xs={12} md={6} key={source.id}>
              <Card 
                sx={{
                  border: isSelected ? 2 : 1,
                  borderColor: isSelected ? 'primary.main' : 'divider',
                  cursor: 'pointer',
                  transition: 'all 0.2s ease-in-out',
                  '&:hover': {
                    boxShadow: 2,
                    borderColor: 'primary.light',
                  },
                }}
                onClick={() => handleSelectionChange(source.id, !isSelected)}
              >
                <CardContent>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                    {getSourceIcon(source.type, source.format)}
                    <Typography variant="h6" sx={{ ml: 1, flex: 1 }}>
                      {source.name}
                    </Typography>
                    {isSelected && <CheckIcon color="primary" />}
                  </Box>

                  <Box sx={{ mb: 2 }}>
                    <Chip
                      label={source.format.toUpperCase()}
                      size="small"
                      color={getFormatColor(source.format)}
                      sx={{ mr: 1 }}
                    />
                    <Chip
                      label={source.type === 'file' ? '文件' : '数据库'}
                      size="small"
                      variant="outlined"
                    />
                  </Box>

                  <Typography variant="body2" color="text.secondary" gutterBottom>
                    大小: {source.size} | 记录数: {source.records.toLocaleString()}
                  </Typography>

                  <Typography variant="caption" color="text.secondary">
                    字段: {source.fields.join(', ')}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          )
        })}

        {/* Add New Source Card */}
        <Grid item xs={12} md={6}>
          <Card
            sx={{
              border: 1,
              borderStyle: 'dashed',
              borderColor: 'divider',
              cursor: 'pointer',
              minHeight: 200,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              '&:hover': {
                borderColor: 'primary.main',
                bgcolor: 'primary.50',
              },
            }}
          >
            <CardContent sx={{ textAlign: 'center' }}>
              <AddIcon sx={{ fontSize: 48, color: 'grey.400', mb: 1 }} />
              <Typography variant="h6" color="text.secondary">
                添加新数据源
              </Typography>
              <Typography variant="body2" color="text.secondary">
                上传文件或连接数据库
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {selectedSources.length > 0 && (
        <Box sx={{ mt: 3, p: 2, bgcolor: 'background.default', borderRadius: 1 }}>
          <Typography variant="subtitle2" gutterBottom>
            已选择的数据源 ({selectedSources.length})
          </Typography>
          <List dense>
            {mockDataSources
              .filter(source => selectedSources.includes(source.id))
              .map((source) => (
                <ListItem key={source.id}>
                  <ListItemIcon>
                    {getSourceIcon(source.type, source.format)}
                  </ListItemIcon>
                  <ListItemText
                    primary={source.name}
                    secondary={`${source.records.toLocaleString()} 条记录`}
                  />
                  <ListItemSecondaryAction>
                    <Checkbox
                      edge="end"
                      checked={true}
                      onChange={() => handleSelectionChange(source.id, false)}
                    />
                  </ListItemSecondaryAction>
                </ListItem>
              ))}
          </List>
        </Box>
      )}
    </Box>
  )
}