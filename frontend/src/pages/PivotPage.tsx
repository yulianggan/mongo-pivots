import React from 'react'
import { Box, Card, CardContent, Typography } from '@mui/material'
import { useAppSelector } from '@/hooks/redux'

export const PivotPage: React.FC = () => {
  const { config, isLoading, error } = useAppSelector((state) => state.app)
  
  return (
    <Box>
      <Card>
        <CardContent>
          <Typography variant="h4" gutterBottom>
            数据透视表
          </Typography>
          
          <Typography variant="body1" color="text.secondary" gutterBottom>
            当前集合: {config.collection || '未选择'}
          </Typography>
          
          {isLoading && (
            <Typography color="info.main">
              加载中...
            </Typography>
          )}
          
          {error && (
            <Typography color="error.main">
              错误: {error}
            </Typography>
          )}
          
          {!config.collection && !isLoading && (
            <Typography color="warning.main">
              请先在配置页面选择数据集合
            </Typography>
          )}
        </CardContent>
      </Card>
    </Box>
  )
}