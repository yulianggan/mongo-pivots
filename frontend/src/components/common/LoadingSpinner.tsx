import React from 'react'
import { CircularProgress, Box, Typography } from '@mui/material'

interface LoadingSpinnerProps {
  message?: string
  size?: number
  color?: 'primary' | 'secondary' | 'inherit'
  centered?: boolean
}

export const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({
  message = '加载中...',
  size = 40,
  color = 'primary',
  centered = true,
}) => {
  const content = (
    <>
      <CircularProgress size={size} color={color} />
      {message && (
        <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
          {message}
        </Typography>
      )}
    </>
  )

  if (centered) {
    return (
      <Box
        sx={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          p: 3,
        }}
      >
        {content}
      </Box>
    )
  }

  return content
}