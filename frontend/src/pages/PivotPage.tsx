import React, { useState } from 'react'
import { Box, Card, CardContent, Typography, Button, Tabs, Tab } from '@mui/material'
import { Link } from 'react-router-dom'
import { 
  TableChart as PivotIcon, 
  ViewList as RawDataIcon 
} from '@mui/icons-material'
import { useAppSelector } from '@/hooks/redux'
import { useData } from '@/hooks/useApi'
import { LoadingSpinner, ErrorAlert, DataTable } from '@/components/common'
import { PivotLayout } from '@/components/pivot/PivotLayout'

export const PivotPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState(0)
  const { config, error } = useAppSelector((state) => state.app)
  const { data: pivotData, isLoading, error: dataError, refetch } = useData(
    config.collection, 
    !!config.collection
  )
  
  if (!config.collection) {
    return (
      <Box>
        <Card>
          <CardContent sx={{ textAlign: 'center', py: 6 }}>
            <Typography variant="h5" gutterBottom>
              欢迎使用数据透视表
            </Typography>
            
            <Typography variant="body1" color="text.secondary" gutterBottom sx={{ mb: 3 }}>
              请先在配置页面选择数据集合，然后开始数据分析
            </Typography>
            
            <Button 
              variant="contained" 
              component={Link} 
              to="/config"
              size="large"
            >
              前往配置
            </Button>
          </CardContent>
        </Card>
      </Box>
    )
  }
  
  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        数据透视表
      </Typography>
      
      <Typography variant="body1" color="text.secondary" gutterBottom sx={{ mb: 3 }}>
        当前集合: <strong>{config.collection}</strong> | 
        数据限制: <strong>{config.limit}</strong> 条 |
        跳过: <strong>{config.skip}</strong> 条
      </Typography>
      
      {error && (
        <Box sx={{ mb: 2 }}>
          <ErrorAlert message={error} />
        </Box>
      )}
      
      {dataError && (
        <Box sx={{ mb: 2 }}>
          <ErrorAlert 
            message={dataError.message} 
            onRetry={() => refetch()} 
          />
        </Box>
      )}
      
      {isLoading && (
        <LoadingSpinner message="正在加载数据..." />
      )}
      
      {/* Tabs Navigation */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs 
          value={activeTab} 
          onChange={(_, newValue) => setActiveTab(newValue)}
          aria-label="pivot table tabs"
        >
          <Tab 
            icon={<PivotIcon />} 
            label="透视表配置" 
            iconPosition="start"
          />
          <Tab 
            icon={<RawDataIcon />} 
            label="原始数据" 
            iconPosition="start"
            disabled={!pivotData || pivotData.length === 0}
          />
        </Tabs>
      </Box>
      
      {/* Tab Content */}
      {activeTab === 0 && (
        <PivotLayout />
      )}
      
      {activeTab === 1 && pivotData && pivotData.length > 0 && (
        <DataTable
          data={pivotData}
          title="原始数据预览"
          maxHeight={600}
          pagination={true}
          pageSize={50}
        />
      )}
      
      {activeTab === 1 && pivotData && pivotData.length === 0 && (
        <Card>
          <CardContent sx={{ textAlign: 'center', py: 4 }}>
            <Typography color="text.secondary">
              当前筛选条件下没有找到数据
            </Typography>
          </CardContent>
        </Card>
      )}
    </Box>
  )
}