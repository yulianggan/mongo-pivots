import React, { useState } from 'react'
import {
  Paper,
  Typography,
  TextField,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Chip,
  Box,
  InputAdornment,
  Divider,
} from '@mui/material'
import {
  Search as SearchIcon,
  Functions as FunctionIcon,
  TableChart as TableIcon,
  Visibility as VisibilityIcon,
  VisibilityOff as VisibilityOffIcon,
} from '@mui/icons-material'

interface FieldSelectorProps {
  fields: string[]
  hiddenFields?: Set<string>
  onFieldVisibilityToggle?: (field: string) => void
  onFieldDragStart?: (field: string) => void
  searchable?: boolean
  title?: string
}

export const FieldSelector: React.FC<FieldSelectorProps> = ({
  fields,
  hiddenFields = new Set(),
  onFieldVisibilityToggle,
  onFieldDragStart,
  searchable = true,
  title = '可用字段',
}) => {
  const [searchTerm, setSearchTerm] = useState('')

  const getFieldType = (fieldName: string): 'dimension' | 'measure' => {
    // Simple heuristic to determine field type
    const measureKeywords = ['count', 'sum', 'avg', 'amount', 'price', 'total', 'quantity', 'value']
    const lowerField = fieldName.toLowerCase()
    
    return measureKeywords.some(keyword => lowerField.includes(keyword)) ? 'measure' : 'dimension'
  }

  const getFieldIcon = (fieldName: string): React.ReactNode => {
    const type = getFieldType(fieldName)
    return type === 'measure' ? 
      <FunctionIcon color="secondary" fontSize="small" /> : 
      <TableIcon color="primary" fontSize="small" />
  }

  const filteredFields = fields.filter(field => 
    field.toLowerCase().includes(searchTerm.toLowerCase())
  )

  const visibleFields = filteredFields.filter(field => !hiddenFields.has(field))
  const hiddenFieldsList = filteredFields.filter(field => hiddenFields.has(field))

  return (
    <Paper sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <Box sx={{ p: 2, borderBottom: 1, borderColor: 'divider' }}>
        <Typography variant="h6" gutterBottom>
          {title}
        </Typography>
        
        {searchable && (
          <TextField
            placeholder="搜索字段..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            size="small"
            fullWidth
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon />
                </InputAdornment>
              ),
            }}
          />
        )}
        
        <Box sx={{ mt: 2, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          <Chip
            size="small"
            icon={<TableIcon />}
            label="维度字段"
            color="primary"
            variant="outlined"
          />
          <Chip
            size="small"
            icon={<FunctionIcon />}
            label="度量字段"
            color="secondary"
            variant="outlined"
          />
        </Box>
      </Box>
      
      <Box sx={{ flex: 1, overflow: 'auto' }}>
        <List dense>
          {visibleFields.map((field) => (
            <ListItem
              key={field}
              draggable
              onDragStart={() => onFieldDragStart?.(field)}
              sx={{
                cursor: 'grab',
                '&:hover': {
                  backgroundColor: 'action.hover',
                },
                '&:active': {
                  cursor: 'grabbing',
                },
              }}
              secondaryAction={
                onFieldVisibilityToggle && (
                  <VisibilityIcon
                    fontSize="small"
                    sx={{ 
                      cursor: 'pointer',
                      color: 'action.active',
                      '&:hover': { color: 'primary.main' }
                    }}
                    onClick={() => onFieldVisibilityToggle(field)}
                  />
                )
              }
            >
              <ListItemIcon sx={{ minWidth: 32 }}>
                {getFieldIcon(field)}
              </ListItemIcon>
              <ListItemText
                primary={field}
                primaryTypographyProps={{
                  variant: 'body2',
                  noWrap: true,
                }}
              />
            </ListItem>
          ))}
          
          {hiddenFieldsList.length > 0 && (
            <>
              <Divider />
              <ListItem>
                <Typography variant="subtitle2" color="text.secondary">
                  隐藏字段 ({hiddenFieldsList.length})
                </Typography>
              </ListItem>
              {hiddenFieldsList.map((field) => (
                <ListItem
                  key={`hidden-${field}`}
                  sx={{
                    opacity: 0.5,
                  }}
                  secondaryAction={
                    onFieldVisibilityToggle && (
                      <VisibilityOffIcon
                        fontSize="small"
                        sx={{ 
                          cursor: 'pointer',
                          color: 'action.disabled',
                          '&:hover': { color: 'primary.main' }
                        }}
                        onClick={() => onFieldVisibilityToggle(field)}
                      />
                    )
                  }
                >
                  <ListItemIcon sx={{ minWidth: 32 }}>
                    {getFieldIcon(field)}
                  </ListItemIcon>
                  <ListItemText
                    primary={field}
                    primaryTypographyProps={{
                      variant: 'body2',
                      noWrap: true,
                    }}
                  />
                </ListItem>
              ))}
            </>
          )}
        </List>
      </Box>
      
      <Box sx={{ p: 1, borderTop: 1, borderColor: 'divider' }}>
        <Typography variant="caption" color="text.secondary">
          总计 {fields.length} 个字段 | 可见 {visibleFields.length} 个
        </Typography>
      </Box>
    </Paper>
  )
}