import React, { useState, useEffect } from 'react'
import {
  Box,
  Typography,
  Grid,
  Card,
  CardHeader,
  CardContent,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Alert,
} from '@mui/material'

interface FieldMappingProps {
  previewData: Record<string, any[]>
  fieldMappings: any[]
  onUpdate: (fieldMappings: any[]) => void
}

export const FieldMapping: React.FC<FieldMappingProps> = ({
  previewData,
  fieldMappings,
  onUpdate,
}) => {
  const [mappings, setMappings] = useState<Record<string, Record<string, string>>>({})

  const dataSources = Object.keys(previewData)

  useEffect(() => {
    if (dataSources.length >= 2) {
      // Auto-detect potential field mappings
      const autoMappings: Record<string, Record<string, string>> = {}
      
      const source1 = dataSources[0]
      const source2 = dataSources[1]
      
      const fields1 = previewData[source1] ? Object.keys(previewData[source1][0] || {}) : []
      const fields2 = previewData[source2] ? Object.keys(previewData[source2][0] || {}) : []
      
      // Simple field matching logic
      fields1.forEach(field1 => {
        const matchingField = fields2.find(field2 => 
          field1 === field2 || 
          field1.includes('customer') && field2.includes('customer') ||
          field1.includes('id') && field2.includes('id')
        )
        
        if (matchingField) {
          if (!autoMappings[source1]) autoMappings[source1] = {}
          if (!autoMappings[source2]) autoMappings[source2] = {}
          
          autoMappings[source1][field1] = matchingField
          autoMappings[source2][matchingField] = field1
        }
      })
      
      setMappings(autoMappings)
      
      // Update parent
      const mappingArray = Object.entries(autoMappings).map(([sourceId, fieldMap]) => ({
        sourceId,
        fieldMap,
      }))
      onUpdate(mappingArray)
    }
  }, [previewData, onUpdate, dataSources])

  const handleFieldMappingChange = (sourceId: string, sourceField: string, targetField: string) => {
    const newMappings = { ...mappings }
    if (!newMappings[sourceId]) newMappings[sourceId] = {}
    newMappings[sourceId][sourceField] = targetField
    
    setMappings(newMappings)
    
    // Update parent
    const mappingArray = Object.entries(newMappings).map(([sourceId, fieldMap]) => ({
      sourceId,
      fieldMap,
    }))
    onUpdate(mappingArray)
  }

  if (dataSources.length < 2) {
    return (
      <Box textAlign="center" py={4}>
        <Typography variant="body1" color="text.secondary">
          请先选择至少2个数据源进行字段映射
        </Typography>
      </Box>
    )
  }

  const source1 = dataSources[0]
  const source2 = dataSources[1]
  const fields1 = previewData[source1] ? Object.keys(previewData[source1][0] || {}) : []
  const fields2 = previewData[source2] ? Object.keys(previewData[source2][0] || {}) : []

  return (
    <Box>
      <Typography variant="h6" gutterBottom>
        字段映射配置
      </Typography>
      
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        配置数据源之间的字段对应关系。系统已自动检测可能的匹配字段。
      </Typography>

      <Alert severity="info" sx={{ mb: 3 }}>
        已自动检测到 {Object.values(mappings[source1] || {}).length} 个字段匹配
      </Alert>

      <Grid container spacing={3}>
        <Grid item xs={12} md={6}>
          <Card>
            <CardHeader title={source1} subheader="源数据字段" />
            <CardContent>
              {fields1.map(field => (
                <Box key={field} sx={{ mb: 2 }}>
                  <Typography variant="body2" gutterBottom>
                    {field}
                  </Typography>
                  <FormControl fullWidth size="small">
                    <InputLabel>映射到 {source2}</InputLabel>
                    <Select
                      value={mappings[source1]?.[field] || ''}
                      onChange={(e) => handleFieldMappingChange(source1, field, e.target.value)}
                    >
                      <MenuItem value="">-- 不映射 --</MenuItem>
                      {fields2.map(field2 => (
                        <MenuItem key={field2} value={field2}>
                          {field2}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Box>
              ))}
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={6}>
          <Card>
            <CardHeader title={source2} subheader="目标数据字段" />
            <CardContent>
              {fields2.map(field => (
                <Box key={field} sx={{ mb: 2 }}>
                  <Typography variant="body2" gutterBottom>
                    {field}
                  </Typography>
                  <FormControl fullWidth size="small">
                    <InputLabel>映射到 {source1}</InputLabel>
                    <Select
                      value={mappings[source2]?.[field] || ''}
                      onChange={(e) => handleFieldMappingChange(source2, field, e.target.value)}
                    >
                      <MenuItem value="">-- 不映射 --</MenuItem>
                      {fields1.map(field1 => (
                        <MenuItem key={field1} value={field1}>
                          {field1}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Box>
              ))}
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Mapping Summary */}
      <Box sx={{ mt: 3, p: 2, bgcolor: 'background.default', borderRadius: 1 }}>
        <Typography variant="subtitle2" gutterBottom>
          字段映射摘要
        </Typography>
        {Object.entries(mappings[source1] || {}).map(([sourceField, targetField]) => (
          <Typography key={sourceField} variant="body2" color="text.secondary">
            {source1}.{sourceField} ↔ {source2}.{targetField}
          </Typography>
        ))}
      </Box>
    </Box>
  )
}