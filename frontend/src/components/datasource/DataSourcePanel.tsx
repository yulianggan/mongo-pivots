import React, { useState, useRef } from 'react'
import {
  Paper,
  Box,
  Typography,
  Button,
  LinearProgress,
  Alert,
  Chip,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  ListItemSecondaryAction,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
} from '@mui/material'
import {
  CloudUpload as UploadIcon,
  InsertDriveFile as FileIcon,
  TableChart as TableIcon,
  Delete as DeleteIcon,
  Preview as PreviewIcon,
  CheckCircle as SuccessIcon,
  Error as ErrorIcon,
} from '@mui/icons-material'
import { DataTable } from '@/components/common'

interface DataSource {
  id: string
  name: string
  type: 'csv' | 'excel' | 'json'
  size: number
  uploadedAt: string
  status: 'uploading' | 'processing' | 'ready' | 'error'
  progress?: number
  error?: string
  preview?: any[]
}

export const DataSourcePanel: React.FC = () => {
  const [dataSources, setDataSources] = useState<DataSource[]>([])
  const [isDragOver, setIsDragOver] = useState(false)
  const [previewDialog, setPreviewDialog] = useState<DataSource | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleFileSelect = (files: FileList | null): void => {
    if (!files) return
    
    Array.from(files).forEach(file => {
      const dataSource: DataSource = {
        id: Math.random().toString(36).substr(2, 9),
        name: file.name,
        type: getFileType(file.name),
        size: file.size,
        uploadedAt: new Date().toISOString(),
        status: 'uploading',
        progress: 0,
      }
      
      setDataSources(prev => [...prev, dataSource])
      simulateUpload(dataSource.id, file)
    })
  }

  const getFileType = (filename: string): 'csv' | 'excel' | 'json' => {
    const ext = filename.toLowerCase().split('.').pop()
    switch (ext) {
      case 'xlsx':
      case 'xls':
        return 'excel'
      case 'json':
        return 'json'
      default:
        return 'csv'
    }
  }

  const simulateUpload = async (id: string, file: File): Promise<void> => {
    try {
      // Simulate upload progress
      for (let progress = 0; progress <= 100; progress += 10) {
        await new Promise(resolve => setTimeout(resolve, 100))
        setDataSources(prev => prev.map(ds => 
          ds.id === id ? { ...ds, progress } : ds
        ))
      }
      
      // Simulate processing
      setDataSources(prev => prev.map(ds => 
        ds.id === id ? { ...ds, status: 'processing', progress: undefined } : ds
      ))
      
      await new Promise(resolve => setTimeout(resolve, 1000))
      
      // Generate mock preview data
      const mockPreview = generateMockPreview(file.name)
      
      // Mark as ready
      setDataSources(prev => prev.map(ds => 
        ds.id === id ? { 
          ...ds, 
          status: 'ready', 
          preview: mockPreview 
        } : ds
      ))
    } catch (error) {
      setDataSources(prev => prev.map(ds => 
        ds.id === id ? { 
          ...ds, 
          status: 'error', 
          error: '文件处理失败'
        } : ds
      ))
    }
  }

  const generateMockPreview = (filename: string): any[] => {
    const isCustomers = filename.toLowerCase().includes('customer')
    const isOrders = filename.toLowerCase().includes('order')
    
    if (isCustomers) {
      return [
        { customer_id: 'C001', name: '张三', email: 'zhangsan@example.com', city: '北京', created_at: '2023-01-15' },
        { customer_id: 'C002', name: '李四', email: 'lisi@example.com', city: '上海', created_at: '2023-01-16' },
        { customer_id: 'C003', name: '王五', email: 'wangwu@example.com', city: '广州', created_at: '2023-01-17' },
      ]
    }
    
    if (isOrders) {
      return [
        { order_id: 'O001', customer_id: 'C001', amount: 299.99, status: 'completed', order_date: '2023-03-15' },
        { order_id: 'O002', customer_id: 'C002', amount: 159.50, status: 'pending', order_date: '2023-03-16' },
        { order_id: 'O003', customer_id: 'C001', amount: 89.99, status: 'completed', order_date: '2023-03-17' },
      ]
    }
    
    return [
      { id: 1, field1: 'value1', field2: 'value2', field3: 100 },
      { id: 2, field1: 'value3', field2: 'value4', field3: 200 },
      { id: 3, field1: 'value5', field2: 'value6', field3: 300 },
    ]
  }

  const handleDragOver = (e: React.DragEvent): void => {
    e.preventDefault()
    setIsDragOver(true)
  }

  const handleDragLeave = (e: React.DragEvent): void => {
    e.preventDefault()
    setIsDragOver(false)
  }

  const handleDrop = (e: React.DragEvent): void => {
    e.preventDefault()
    setIsDragOver(false)
    handleFileSelect(e.dataTransfer.files)
  }

  const handleDelete = (id: string): void => {
    setDataSources(prev => prev.filter(ds => ds.id !== id))
  }

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes'
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  const getStatusIcon = (status: DataSource['status']) => {
    switch (status) {
      case 'ready':
        return <SuccessIcon color="success" />
      case 'error':
        return <ErrorIcon color="error" />
      case 'processing':
        return <TableIcon color="primary" />
      default:
        return <FileIcon />
    }
  }

  const getStatusColor = (status: DataSource['status']): 'default' | 'primary' | 'secondary' | 'error' | 'info' | 'success' | 'warning' => {
    switch (status) {
      case 'ready':
        return 'success'
      case 'error':
        return 'error'
      case 'processing':
        return 'info'
      case 'uploading':
        return 'primary'
      default:
        return 'default'
    }
  }

  const getStatusText = (status: DataSource['status']): string => {
    switch (status) {
      case 'ready':
        return '就绪'
      case 'error':
        return '错误'
      case 'processing':
        return '处理中'
      case 'uploading':
        return '上传中'
      default:
        return '未知'
    }
  }

  return (
    <>
      <Paper sx={{ p: 3, mb: 2 }}>
        {/* Upload Area */}
        <Box
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          sx={{
            border: 2,
            borderStyle: 'dashed',
            borderColor: isDragOver ? 'primary.main' : 'grey.300',
            borderRadius: 2,
            p: 4,
            textAlign: 'center',
            bgcolor: isDragOver ? 'primary.50' : 'grey.50',
            cursor: 'pointer',
            transition: 'all 0.2s ease-in-out',
            '&:hover': {
              borderColor: 'primary.main',
              bgcolor: 'primary.50',
            },
          }}
          onClick={() => fileInputRef.current?.click()}
        >
          <UploadIcon sx={{ fontSize: 48, color: 'grey.400', mb: 2 }} />
          <Typography variant="h6" gutterBottom>
            {isDragOver ? '松开以上传文件' : '拖拽文件到此处或点击上传'}
          </Typography>
          <Typography variant="body2" color="text.secondary" gutterBottom>
            支持 CSV、Excel (.xlsx/.xls)、JSON 格式
          </Typography>
          <Button
            variant="contained"
            startIcon={<UploadIcon />}
            sx={{ mt: 2 }}
            onClick={(e) => {
              e.stopPropagation()
              fileInputRef.current?.click()
            }}
          >
            选择文件
          </Button>
        </Box>

        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".csv,.xlsx,.xls,.json"
          style={{ display: 'none' }}
          onChange={(e) => handleFileSelect(e.target.files)}
        />
      </Paper>

      {/* Data Sources List */}
      {dataSources.length > 0 && (
        <Paper>
          <Box sx={{ p: 2, borderBottom: 1, borderColor: 'divider' }}>
            <Typography variant="h6">
              数据源列表 ({dataSources.length})
            </Typography>
          </Box>
          
          <List>
            {dataSources.map((dataSource) => (
              <ListItem key={dataSource.id}>
                <ListItemIcon>
                  {getStatusIcon(dataSource.status)}
                </ListItemIcon>
                
                <ListItemText
                  primary={
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <Typography variant="subtitle2">
                        {dataSource.name}
                      </Typography>
                      <Chip
                        label={getStatusText(dataSource.status)}
                        size="small"
                        color={getStatusColor(dataSource.status)}
                        variant="outlined"
                      />
                    </Box>
                  }
                  secondary={
                    <Box>
                      <Typography variant="caption" display="block">
                        {formatFileSize(dataSource.size)} • {new Date(dataSource.uploadedAt).toLocaleString()}
                      </Typography>
                      
                      {dataSource.status === 'uploading' && dataSource.progress !== undefined && (
                        <Box sx={{ mt: 1 }}>
                          <LinearProgress 
                            variant="determinate" 
                            value={dataSource.progress} 
                            sx={{ height: 4, borderRadius: 2 }}
                          />
                          <Typography variant="caption" color="text.secondary">
                            {dataSource.progress}%
                          </Typography>
                        </Box>
                      )}
                      
                      {dataSource.status === 'processing' && (
                        <Box sx={{ mt: 1 }}>
                          <LinearProgress sx={{ height: 4, borderRadius: 2 }} />
                          <Typography variant="caption" color="text.secondary">
                            正在处理文件...
                          </Typography>
                        </Box>
                      )}
                      
                      {dataSource.error && (
                        <Alert severity="error" sx={{ mt: 1 }}>
                          {dataSource.error}
                        </Alert>
                      )}
                    </Box>
                  }
                />
                
                <ListItemSecondaryAction>
                  <Box sx={{ display: 'flex', gap: 1 }}>
                    {dataSource.status === 'ready' && dataSource.preview && (
                      <IconButton
                        edge="end"
                        onClick={() => setPreviewDialog(dataSource)}
                        title="预览数据"
                      >
                        <PreviewIcon />
                      </IconButton>
                    )}
                    <IconButton
                      edge="end"
                      onClick={() => handleDelete(dataSource.id)}
                      title="删除"
                    >
                      <DeleteIcon />
                    </IconButton>
                  </Box>
                </ListItemSecondaryAction>
              </ListItem>
            ))}
          </List>
        </Paper>
      )}

      {/* Preview Dialog */}
      <Dialog
        open={!!previewDialog}
        onClose={() => setPreviewDialog(null)}
        maxWidth="lg"
        fullWidth
      >
        <DialogTitle>
          数据预览: {previewDialog?.name}
        </DialogTitle>
        <DialogContent>
          {previewDialog?.preview && (
            <DataTable
              data={previewDialog.preview}
              maxHeight={400}
              pagination={true}
              pageSize={10}
            />
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPreviewDialog(null)}>
            关闭
          </Button>
        </DialogActions>
      </Dialog>
    </>
  )
}