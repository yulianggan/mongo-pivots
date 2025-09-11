import React, { useState, useEffect } from 'react'
import {
  Box,
  Typography,
  Grid,
  Card,
  CardContent,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Divider,
  Alert,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  TextField,
  Switch,
  FormControlLabel,
} from '@mui/material'
import {
  Storage as DataIcon,
  AccountTree as MappingIcon,
  Settings as ConfigIcon,
  PlayArrow as ExecuteIcon,
  Cloud as StorageIcon,
} from '@mui/icons-material'

interface ExecutionConfirmationProps {
  wizardData: any
  onUpdate: (executionSettings: any) => void
}

export const ExecutionConfirmation: React.FC<ExecutionConfirmationProps> = ({
  wizardData,
  onUpdate,
}) => {
  const [outputSettings, setOutputSettings] = useState({
    outputName: 'joined_data',
    saveToCollection: true,
    collectionName: 'joined_results',
    downloadCsv: false,
    maxRecords: 10000,
  })

  useEffect(() => {
    onUpdate({
      ...outputSettings,
      timestamp: new Date().toISOString(),
    })
  }, [outputSettings, onUpdate])

  const handleSettingChange = (field: string, value: any): void => {
    setOutputSettings(prev => ({
      ...prev,
      [field]: value,
    }))
  }

  return (
    <Box>
      <Typography variant="h6" gutterBottom>
        执行确认
      </Typography>
      
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        确认连接配置并设置输出选项。点击"完成配置"开始执行连接操作。
      </Typography>

      <Grid container spacing={3}>
        <Grid item xs={12} md={8}>
          {/* Configuration Review */}
          <Card sx={{ mb: 3 }}>
            <CardContent>
              <Typography variant="subtitle1" gutterBottom>
                配置审查
              </Typography>
              
              <List>
                <ListItem>
                  <ListItemIcon>
                    <DataIcon color="primary" />
                  </ListItemIcon>
                  <ListItemText
                    primary="数据源"
                    secondary={`已选择 ${wizardData.dataSources?.length || 0} 个数据源: ${
                      wizardData.dataSources?.map((ds: any) => ds.name).join(', ') || '无'
                    }`}
                  />
                </ListItem>
                
                <Divider component="li" />
                
                <ListItem>
                  <ListItemIcon>
                    <MappingIcon color="secondary" />
                  </ListItemIcon>
                  <ListItemText
                    primary="字段映射"
                    secondary={`已配置 ${wizardData.fieldMappings?.length || 0} 个字段映射`}
                  />
                </ListItem>
                
                <Divider component="li" />
                
                <ListItem>
                  <ListItemIcon>
                    <ConfigIcon color="success" />
                  </ListItemIcon>
                  <ListItemText
                    primary="连接配置"
                    secondary={`连接类型: ${wizardData.joinConfig?.joinType || '未设置'} | 
                              条件: ${wizardData.joinConfig?.conditions?.length || 0} 个 |
                              预估结果: ${wizardData.joinConfig?.estimatedResults?.toLocaleString() || 0} 条`}
                  />
                </ListItem>
              </List>
            </CardContent>
          </Card>

          {/* Output Settings */}
          <Card>
            <CardContent>
              <Typography variant="subtitle1" gutterBottom>
                输出设置
              </Typography>
              
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                <TextField
                  label="输出名称"
                  value={outputSettings.outputName}
                  onChange={(e) => handleSettingChange('outputName', e.target.value)}
                  fullWidth
                  size="small"
                />
                
                <FormControlLabel
                  control={
                    <Switch
                      checked={outputSettings.saveToCollection}
                      onChange={(e) => handleSettingChange('saveToCollection', e.target.checked)}
                    />
                  }
                  label="保存到数据库集合"
                />
                
                {outputSettings.saveToCollection && (
                  <TextField
                    label="集合名称"
                    value={outputSettings.collectionName}
                    onChange={(e) => handleSettingChange('collectionName', e.target.value)}
                    fullWidth
                    size="small"
                    sx={{ ml: 3 }}
                  />
                )}
                
                <FormControlLabel
                  control={
                    <Switch
                      checked={outputSettings.downloadCsv}
                      onChange={(e) => handleSettingChange('downloadCsv', e.target.checked)}
                    />
                  }
                  label="同时下载CSV文件"
                />
                
                <TextField
                  label="最大记录数限制"
                  type="number"
                  value={outputSettings.maxRecords}
                  onChange={(e) => handleSettingChange('maxRecords', parseInt(e.target.value))}
                  fullWidth
                  size="small"
                  inputProps={{ min: 1, max: 100000 }}
                />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={4}>
          {/* Execution Summary */}
          <Card>
            <CardContent>
              <Typography variant="subtitle1" gutterBottom>
                执行摘要
              </Typography>
              
              <List dense>
                <ListItem>
                  <ListItemIcon>
                    <DataIcon fontSize="small" />
                  </ListItemIcon>
                  <ListItemText
                    primary="数据源"
                    secondary={`${wizardData.dataSources?.length || 0} 个`}
                  />
                </ListItem>
                
                <ListItem>
                  <ListItemIcon>
                    <ConfigIcon fontSize="small" />
                  </ListItemIcon>
                  <ListItemText
                    primary="连接类型"
                    secondary={wizardData.joinConfig?.joinType || '未设置'}
                  />
                </ListItem>
                
                <ListItem>
                  <ListItemIcon>
                    <ExecuteIcon fontSize="small" />
                  </ListItemIcon>
                  <ListItemText
                    primary="预估结果"
                    secondary={`${wizardData.joinConfig?.estimatedResults?.toLocaleString() || 0} 条记录`}
                  />
                </ListItem>
                
                <ListItem>
                  <ListItemIcon>
                    <StorageIcon fontSize="small" />
                  </ListItemIcon>
                  <ListItemText
                    primary="输出位置"
                    secondary={outputSettings.saveToCollection ? outputSettings.collectionName : '仅下载'}
                  />
                </ListItem>
              </List>
            </CardContent>
          </Card>

          {/* Warnings and Recommendations */}
          <Alert severity="info" sx={{ mt: 2 }}>
            <Typography variant="subtitle2" gutterBottom>
              执行提示
            </Typography>
            <Typography variant="body2">
              • 大数据集连接可能需要较长时间
            </Typography>
            <Typography variant="body2">
              • 建议先用小数据集测试配置
            </Typography>
            <Typography variant="body2">
              • 执行过程中可以在进度页面查看状态
            </Typography>
          </Alert>
        </Grid>
      </Grid>
    </Box>
  )
}