import React, { useState, useEffect } from 'react'
import {
  Box,
  Typography,
  Grid,
  Card,
  CardContent,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Alert,
  Chip,
} from '@mui/material'

interface JoinConfigurationProps {
  fieldMappings: any[]
  joinConfig: any
  onUpdate: (joinConfig: any) => void
}

const joinTypes = [
  { value: 'inner', label: 'Inner Join', description: '只保留两个数据源中都存在的记录' },
  { value: 'left', label: 'Left Join', description: '保留左侧数据源的所有记录' },
  { value: 'right', label: 'Right Join', description: '保留右侧数据源的所有记录' },
  { value: 'full', label: 'Full Outer Join', description: '保留两个数据源中的所有记录' },
  { value: 'semi', label: 'Semi Join', description: '只保留左侧数据源中有匹配的记录' },
  { value: 'anti', label: 'Anti Join', description: '只保留左侧数据源中没有匹配的记录' },
]

export const JoinConfiguration: React.FC<JoinConfigurationProps> = ({
  fieldMappings,
  joinConfig,
  onUpdate,
}) => {
  const [selectedJoinType, setSelectedJoinType] = useState('inner')
  const [joinConditions, setJoinConditions] = useState<string[]>([])

  useEffect(() => {
    // Auto-detect join conditions from field mappings
    const conditions: string[] = []
    
    fieldMappings.forEach(mapping => {
      Object.entries(mapping.fieldMap || {}).forEach(([sourceField, targetField]) => {
        if (targetField) {
          conditions.push(`${mapping.sourceId}.${sourceField} = ${targetField}`)
        }
      })
    })
    
    setJoinConditions(conditions)
    
    // Update parent
    onUpdate({
      joinType: selectedJoinType,
      conditions: conditions,
      estimatedResults: calculateEstimatedResults(selectedJoinType, conditions.length),
    })
  }, [fieldMappings, selectedJoinType, onUpdate])

  const calculateEstimatedResults = (joinType: string, conditionCount: number): number => {
    // Mock estimation logic
    const baseRecords = 1000
    const multiplier = joinType === 'full' ? 1.5 : joinType === 'inner' ? 0.7 : 1.0
    const conditionMultiplier = Math.max(0.1, 1 - (conditionCount - 1) * 0.2)
    
    return Math.floor(baseRecords * multiplier * conditionMultiplier)
  }

  const handleJoinTypeChange = (newJoinType: string): void => {
    setSelectedJoinType(newJoinType)
    onUpdate({
      joinType: newJoinType,
      conditions: joinConditions,
      estimatedResults: calculateEstimatedResults(newJoinType, joinConditions.length),
    })
  }

  if (fieldMappings.length === 0) {
    return (
      <Box textAlign="center" py={4}>
        <Typography variant="body1" color="text.secondary">
          请先完成字段映射配置
        </Typography>
      </Box>
    )
  }

  const selectedJoinTypeInfo = joinTypes.find(jt => jt.value === selectedJoinType)

  return (
    <Box>
      <Typography variant="h6" gutterBottom>
        连接配置
      </Typography>
      
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        选择连接类型并确认连接条件。系统将基于字段映射自动生成连接条件。
      </Typography>

      <Grid container spacing={3}>
        <Grid item xs={12} md={8}>
          {/* Join Type Selection */}
          <Card sx={{ mb: 3 }}>
            <CardContent>
              <Typography variant="subtitle1" gutterBottom>
                连接类型
              </Typography>
              
              <FormControl fullWidth sx={{ mb: 2 }}>
                <InputLabel>选择连接类型</InputLabel>
                <Select
                  value={selectedJoinType}
                  onChange={(e) => handleJoinTypeChange(e.target.value)}
                  label="选择连接类型"
                >
                  {joinTypes.map(joinType => (
                    <MenuItem key={joinType.value} value={joinType.value}>
                      {joinType.label}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>

              {selectedJoinTypeInfo && (
                <Alert severity="info">
                  {selectedJoinTypeInfo.description}
                </Alert>
              )}
            </CardContent>
          </Card>

          {/* Join Conditions */}
          <Card>
            <CardContent>
              <Typography variant="subtitle1" gutterBottom>
                连接条件
              </Typography>
              
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                基于字段映射自动生成的连接条件：
              </Typography>

              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                {joinConditions.map((condition, index) => (
                  <Chip
                    key={index}
                    label={condition}
                    variant="outlined"
                    color="primary"
                  />
                ))}
              </Box>

              {joinConditions.length === 0 && (
                <Alert severity="warning">
                  未检测到有效的连接条件，请检查字段映射配置
                </Alert>
              )}
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={4}>
          {/* Configuration Summary */}
          <Card>
            <CardContent>
              <Typography variant="subtitle1" gutterBottom>
                配置摘要
              </Typography>
              
              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  连接类型
                </Typography>
                <Typography variant="body1">
                  {selectedJoinTypeInfo?.label}
                </Typography>
              </Box>

              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  连接条件数量
                </Typography>
                <Typography variant="body1">
                  {joinConditions.length} 个条件
                </Typography>
              </Box>

              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  预估结果记录数
                </Typography>
                <Typography variant="body1" color="primary">
                  约 {joinConfig.estimatedResults?.toLocaleString() || 0} 条
                </Typography>
              </Box>

              <Alert severity="info" sx={{ mt: 2 }}>
                预估结果基于数据样本计算，实际结果可能有所不同
              </Alert>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  )
}