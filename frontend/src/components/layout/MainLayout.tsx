import React from 'react'
import { Box, Container } from '@mui/material'

interface MainLayoutProps {
  children: React.ReactNode
}

export const MainLayout: React.FC<MainLayoutProps> = ({ children }) => {
  return (
    <Container maxWidth={false} sx={{ px: 2 }}>
      <Box sx={{ 
        display: 'flex',
        flexDirection: 'column',
        minHeight: 'calc(100vh - 120px)', // Account for AppBar height
        gap: 2
      }}>
        {children}
      </Box>
    </Container>
  )
}