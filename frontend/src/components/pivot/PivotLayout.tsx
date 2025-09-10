import React from 'react'
import { Grid, Box, Typography } from '@mui/material'
import {
  ViewColumn as ColumnIcon,
  ViewList as RowIcon,
  Calculate as ValueIcon,
} from '@mui/icons-material'
import { FieldZone } from './FieldZone'
import { FieldSelector } from './FieldSelector'
import { ResponsiveGrid } from '@/components/layout/ResponsiveGrid'
import { useAppSelector, useAppDispatch } from '@/hooks/redux'
import { updateLayout, toggleFieldVisibility } from '@/store/appSlice'
import type { PivotLayout as PivotLayoutType } from '@/types'

export const PivotLayout: React.FC = () => {
  const dispatch = useAppDispatch()
  const { availableFields, hiddenFields, layout } = useAppSelector((state) => state.app)

  const handleLayoutChange = (key: keyof PivotLayoutType, fields: string[]): void => {
    dispatch(updateLayout({ [key]: fields }))
  }

  const handleFieldVisibilityToggle = (field: string): void => {
    dispatch(toggleFieldVisibility(field))
  }

  const fieldSelector = (
    <FieldSelector
      fields={availableFields}
      hiddenFields={hiddenFields}
      onFieldVisibilityToggle={handleFieldVisibilityToggle}
      title="可用字段"
    />
  )

  const pivotZones = (
    <Box>
      <Typography variant="h6" gutterBottom>
        透视表配置
      </Typography>
      
      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          <FieldZone
            title="列字段"
            fields={layout.cols}
            onFieldsChange={(fields) => handleLayoutChange('cols', fields)}
            color="primary"
            icon={<ColumnIcon fontSize="small" sx={{ mr: 1 }} />}
            placeholder="将字段拖拽到此处作为列"
          />
        </Grid>
        
        <Grid item xs={12} md={6}>
          <FieldZone
            title="行字段"
            fields={layout.rows}
            onFieldsChange={(fields) => handleLayoutChange('rows', fields)}
            color="secondary"
            icon={<RowIcon fontSize="small" sx={{ mr: 1 }} />}
            placeholder="将字段拖拽到此处作为行"
          />
        </Grid>
        
        <Grid item xs={12}>
          <FieldZone
            title="数值字段"
            fields={layout.vals}
            onFieldsChange={(fields) => handleLayoutChange('vals', fields)}
            color="success"
            icon={<ValueIcon fontSize="small" sx={{ mr: 1 }} />}
            placeholder="将字段拖拽到此处作为数值"
            acceptedTypes={['measure']}
          />
        </Grid>
      </Grid>
      
      {/* Preview Section */}
      <Box sx={{ mt: 3 }}>
        <Typography variant="h6" gutterBottom>
          配置预览
        </Typography>
        
        <Box sx={{ p: 2, bgcolor: 'background.paper', borderRadius: 1, border: 1, borderColor: 'divider' }}>
          {layout.rows.length === 0 && layout.cols.length === 0 && layout.vals.length === 0 ? (
            <Typography color="text.secondary" sx={{ fontStyle: 'italic' }}>
              请配置至少一个字段来生成透视表
            </Typography>
          ) : (
            <Box>
              <Typography variant="body2" gutterBottom>
                <strong>行:</strong> {layout.rows.join(', ') || '无'}
              </Typography>
              <Typography variant="body2" gutterBottom>
                <strong>列:</strong> {layout.cols.join(', ') || '无'}
              </Typography>
              <Typography variant="body2">
                <strong>数值:</strong> {layout.vals.join(', ') || '无'}
              </Typography>
            </Box>
          )}
        </Box>
      </Box>
    </Box>
  )

  return (
    <ResponsiveGrid
      leftPanel={fieldSelector}
      leftPanelWidth={{ xs: 12, sm: 12, md: 4, lg: 3 }}
      collapsePanelsOnMobile={true}
      spacing={2}
    >
      {pivotZones}
    </ResponsiveGrid>
  )
}