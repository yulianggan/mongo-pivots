import React, { useState } from 'react'
import {
  Paper,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Button,
  Box,
  Typography,
  Alert,
  CircularProgress,
} from '@mui/material'
import { useAppSelector, useAppDispatch } from '@/hooks/redux'
import { useHealthCheck, useCollections, useData } from '@/hooks/useApi'
import { updateConfig } from '@/store/appSlice'

export const ConfigPanel: React.FC = () => {
  const dispatch = useAppDispatch()
  const { config, isLoading, error } = useAppSelector((state) => state.app)
  const [localApiBase, setLocalApiBase] = useState(config.apiBase)
  
  const { data: healthData, isError: healthError, isLoading: healthLoading } = useHealthCheck()
  const { data: collections, isLoading: collectionsLoading } = useCollections()
  const { refetch: refetchData } = useData(config.collection, false)

  const handleApiBaseChange = (): void => {
    dispatch(updateConfig({ apiBase: localApiBase }))
  }

  const handleCollectionChange = (collection: string): void => {
    dispatch(updateConfig({ collection }))
    if (collection) {
      refetchData()
    }
  }

  const handleConfigChange = (field: keyof typeof config, value: string | number): void => {
    dispatch(updateConfig({ [field]: value }))
  }

  return (
    <Paper sx={{ p: 3, mb: 2 }}>
      <Typography variant="h6" gutterBottom>
        配置管理
      </Typography>
      
      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}
      
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        {/* API Base URL */}
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
          <TextField
            label="API Base URL"
            value={localApiBase}
            onChange={(e) => setLocalApiBase(e.target.value)}
            fullWidth
            size="small"
          />
          <Button 
            variant="contained" 
            onClick={handleApiBaseChange}
            disabled={healthLoading}
          >
            连接
          </Button>
          {healthLoading && <CircularProgress size={20} />}
        </Box>
        
        {/* Health Status */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Typography variant="body2">健康状态:</Typography>
          {healthError ? (
            <Typography variant="body2" color="error">
              连接失败
            </Typography>
          ) : healthData?.status === 'ok' ? (
            <Typography variant="body2" color="success.main">
              正常
            </Typography>
          ) : (
            <Typography variant="body2" color="warning.main">
              检查中...
            </Typography>
          )}
        </Box>
        
        {/* Collection Selection */}
        <FormControl size="small" disabled={collectionsLoading || !collections?.length}>
          <InputLabel>数据集合</InputLabel>
          <Select
            value={config.collection}
            onChange={(e) => handleCollectionChange(e.target.value)}
            label="数据集合"
          >
            <MenuItem value="">
              <em>请选择集合</em>
            </MenuItem>
            {collections?.map((collection) => (
              <MenuItem key={collection} value={collection}>
                {collection}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        
        {/* Data Limit */}
        <TextField
          label="数据限制"
          type="number"
          value={config.limit}
          onChange={(e) => handleConfigChange('limit', parseInt(e.target.value))}
          size="small"
          InputProps={{ inputProps: { min: 1, max: 50000 } }}
        />
        
        {/* Skip Offset */}
        <TextField
          label="跳过行数"
          type="number"
          value={config.skip}
          onChange={(e) => handleConfigChange('skip', parseInt(e.target.value))}
          size="small"
          InputProps={{ inputProps: { min: 0 } }}
        />
        
        {isLoading && (
          <Box sx={{ display: 'flex', justifyContent: 'center' }}>
            <CircularProgress />
          </Box>
        )}
      </Box>
    </Paper>
  )
}