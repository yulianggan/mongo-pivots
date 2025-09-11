import React from 'react'
import { Box, Typography } from '@mui/material'
import { JoinWizard } from '@/components/wizard/JoinWizard'

export const JoinWizardPage: React.FC = () => {
  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        数据连接向导
      </Typography>
      
      <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
        通过5步向导轻松配置数据源连接和字段映射
      </Typography>
      
      <JoinWizard />
    </Box>
  )
}