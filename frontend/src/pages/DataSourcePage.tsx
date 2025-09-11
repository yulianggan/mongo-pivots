import React from 'react'
import { Box, Typography, Card, CardContent } from '@mui/material'
import { DataSourcePanel } from '@/components/datasource/DataSourcePanel'
import { useBreakpoints } from '@/components/layout/ResponsiveGrid'

export const DataSourcePage: React.FC = () => {
  const { isMobile } = useBreakpoints()
  
  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        数据源管理
      </Typography>
      
      <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
        上传和管理数据文件，支持CSV、Excel、JSON格式
      </Typography>
      
      <Box sx={{ 
        display: 'flex', 
        flexDirection: isMobile ? 'column' : 'row',
        gap: 2 
      }}>
        <Box sx={{ flex: 1 }}>
          <DataSourcePanel />
        </Box>
        
        {!isMobile && (
          <Box sx={{ width: 300 }}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  使用提示
                </Typography>
                <Typography variant="body2" color="text.secondary" paragraph>
                  • 支持拖拽上传文件
                </Typography>
                <Typography variant="body2" color="text.secondary" paragraph>
                  • 最大文件大小: 500MB
                </Typography>
                <Typography variant="body2" color="text.secondary" paragraph>
                  • 支持断点续传功能
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  • 自动检测文件格式和编码
                </Typography>
              </CardContent>
            </Card>
          </Box>
        )}
      </Box>
    </Box>
  )
}