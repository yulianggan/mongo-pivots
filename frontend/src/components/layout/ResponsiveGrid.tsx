import React from 'react'
import { Grid, useMediaQuery, useTheme } from '@mui/material'

interface ResponsiveGridProps {
  children: React.ReactNode
  spacing?: number
  leftPanel?: React.ReactNode
  rightPanel?: React.ReactNode
  leftPanelWidth?: { xs?: number; sm?: number; md?: number; lg?: number }
  rightPanelWidth?: { xs?: number; sm?: number; md?: number; lg?: number }
  collapsePanelsOnMobile?: boolean
}

export const ResponsiveGrid: React.FC<ResponsiveGridProps> = ({
  children,
  spacing = 2,
  leftPanel,
  rightPanel,
  leftPanelWidth = { xs: 12, sm: 4, md: 3, lg: 2 },
  rightPanelWidth = { xs: 12, sm: 4, md: 3, lg: 2 },
  collapsePanelsOnMobile = true,
}) => {
  const theme = useTheme()
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'))
  
  // Calculate main content width
  const getMainWidth = () => {
    const leftW = leftPanelWidth
    const rightW = rightPanelWidth
    
    return {
      xs: collapsePanelsOnMobile && isMobile ? 12 : 12 - (leftW.xs || 0) - (rightW.xs || 0),
      sm: 12 - (leftW.sm || 0) - (rightW.sm || 0),
      md: 12 - (leftW.md || 0) - (rightW.md || 0),
      lg: 12 - (leftW.lg || 0) - (rightW.lg || 0),
    }
  }
  
  const mainWidth = getMainWidth()
  const showPanelsOnMobile = !collapsePanelsOnMobile || !isMobile
  
  return (
    <Grid container spacing={spacing}>
      {/* Left Panel */}
      {leftPanel && showPanelsOnMobile && (
        <Grid item {...leftPanelWidth}>
          {leftPanel}
        </Grid>
      )}
      
      {/* Main Content */}
      <Grid item {...mainWidth}>
        {children}
      </Grid>
      
      {/* Right Panel */}
      {rightPanel && showPanelsOnMobile && (
        <Grid item {...rightPanelWidth}>
          {rightPanel}
        </Grid>
      )}
      
      {/* Mobile Collapsed Panels */}
      {collapsePanelsOnMobile && isMobile && (
        <>
          {leftPanel && (
            <Grid item xs={12}>
              {leftPanel}
            </Grid>
          )}
          {rightPanel && (
            <Grid item xs={12}>
              {rightPanel}
            </Grid>
          )}
        </>
      )}
    </Grid>
  )
}

// Utility hook for responsive values
export const useResponsiveValue = <T,>(values: {
  xs?: T
  sm?: T
  md?: T
  lg?: T
  xl?: T
}): T | undefined => {
  const theme = useTheme()
  
  const isXl = useMediaQuery(theme.breakpoints.up('xl'))
  const isLg = useMediaQuery(theme.breakpoints.up('lg'))
  const isMd = useMediaQuery(theme.breakpoints.up('md'))
  const isSm = useMediaQuery(theme.breakpoints.up('sm'))
  
  if (isXl && values.xl !== undefined) return values.xl
  if (isLg && values.lg !== undefined) return values.lg
  if (isMd && values.md !== undefined) return values.md
  if (isSm && values.sm !== undefined) return values.sm
  return values.xs
}

// Breakpoint detection hooks
export const useBreakpoints = () => {
  const theme = useTheme()
  
  return {
    isMobile: useMediaQuery(theme.breakpoints.down('sm')),
    isTablet: useMediaQuery(theme.breakpoints.between('sm', 'md')),
    isDesktop: useMediaQuery(theme.breakpoints.up('md')),
    isLarge: useMediaQuery(theme.breakpoints.up('lg')),
    isXLarge: useMediaQuery(theme.breakpoints.up('xl')),
  }
}