import React from 'react'
import { Alert, AlertTitle, Button } from '@mui/material'
import { Refresh as RefreshIcon } from '@mui/icons-material'

interface ErrorAlertProps {
  title?: string
  message: string
  onRetry?: () => void
  variant?: 'filled' | 'outlined' | 'standard'
  severity?: 'error' | 'warning' | 'info'
}

export const ErrorAlert: React.FC<ErrorAlertProps> = ({
  title = '出现错误',
  message,
  onRetry,
  variant = 'standard',
  severity = 'error',
}) => {
  return (
    <Alert 
      severity={severity} 
      variant={variant}
      action={
        onRetry && (
          <Button
            color="inherit"
            size="small"
            onClick={onRetry}
            startIcon={<RefreshIcon />}
          >
            重试
          </Button>
        )
      }
    >
      <AlertTitle>{title}</AlertTitle>
      {message}
    </Alert>
  )
}