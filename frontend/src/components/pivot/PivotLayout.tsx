import React, { useState } from 'react'
import {
  Box,
  Typography,
  Paper,
  Grid,
  Chip,
  Card,
  CardContent,
  CardHeader,
  Button
} from '@mui/material'

interface PivotLayoutProps {
  data?: any[]
  availableFields?: string[]
  fieldTypes?: Record<string, string>
  onPivotUpdate?: (pivotResult: any) => void
}

export const PivotLayout: React.FC<PivotLayoutProps> = ({
  data = [],
  availableFields = [],
  fieldTypes = {},
  onPivotUpdate = () => {}
}) => {
  const [rowFields, setRowFields] = useState<string[]>([])
  const [colFields, setColFields] = useState<string[]>([])
  const [valueFields, setValueFields] = useState<string[]>([])

  const handleCreatePivot = () => {
    const pivotResult = {
      data: data,
      rowFields,
      colFields,
      valueFields,
      summary: "透视表已生成"
    }
    onPivotUpdate(pivotResult)
  }

  return (
    <Box>
      <Grid container spacing={3}>
        <Grid item xs={12} md={6}>
          <Card>
            <CardHeader title="可用字段" />
            <CardContent>
              <Box display="flex" flexWrap="wrap" gap={1}>
                {availableFields.map((field) => (
                  <Chip
                    key={field}
                    label={`${field} (${fieldTypes[field] || 'unknown'})`}
                    variant="outlined"
                    size="small"
                  />
                ))}
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={6}>
          <Card>
            <CardHeader title="透视配置" />
            <CardContent>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                数据行数: {data.length}
              </Typography>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                字段数量: {availableFields.length}
              </Typography>
              <Button 
                variant="contained" 
                onClick={handleCreatePivot}
                sx={{ mt: 2 }}
              >
                生成透视表
              </Button>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  )
}