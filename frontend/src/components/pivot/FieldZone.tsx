import React from 'react'
import {
  Paper,
  Typography,
  Chip,
  Box,
  Tooltip,
} from '@mui/material'
import {
  Close as CloseIcon,
  Functions as FunctionIcon,
  TableChart as TableIcon,
} from '@mui/icons-material'

interface FieldZoneProps {
  title: string
  fields: string[]
  onFieldsChange: (fields: string[]) => void
  allowMultiple?: boolean
  acceptedTypes?: ('dimension' | 'measure')[]
  placeholder?: string
  color?: 'primary' | 'secondary' | 'success' | 'warning'
  icon?: React.ReactNode
}

export const FieldZone: React.FC<FieldZoneProps> = ({
  title,
  fields,
  onFieldsChange,
  allowMultiple = true,
  placeholder = '拖拽字段到此处',
  color = 'primary',
  icon,
}) => {
  const handleRemoveField = (fieldToRemove: string): void => {
    const newFields = fields.filter(field => field !== fieldToRemove)
    onFieldsChange(newFields)
  }

  const getFieldIcon = (fieldName: string): React.ReactNode => {
    // Simple heuristic to determine field type
    const isNumeric = fieldName.includes('count') || 
                     fieldName.includes('sum') || 
                     fieldName.includes('avg') ||
                     fieldName.includes('amount') ||
                     fieldName.includes('price') ||
                     fieldName.includes('total')
    
    return isNumeric ? <FunctionIcon fontSize="small" /> : <TableIcon fontSize="small" />
  }

  return (
    <Paper
      sx={{
        p: 2,
        minHeight: 80,
        border: fields.length === 0 ? '2px dashed' : '1px solid',
        borderColor: fields.length === 0 ? 'grey.300' : `${color}.main`,
        backgroundColor: fields.length === 0 ? 'grey.50' : 'background.paper',
        transition: 'all 0.2s ease-in-out',
        '&:hover': {
          borderColor: `${color}.light`,
          backgroundColor: fields.length === 0 ? 'grey.100' : undefined,
        },
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
        {icon}
        <Typography variant="subtitle2" color={`${color}.main`} sx={{ fontWeight: 600 }}>
          {title}
        </Typography>
        {!allowMultiple && fields.length > 0 && (
          <Typography variant="caption" color="text.secondary" sx={{ ml: 1 }}>
            (单选)
          </Typography>
        )}
      </Box>
      
      {fields.length === 0 ? (
        <Typography variant="body2" color="text.secondary" sx={{ 
          fontStyle: 'italic',
          textAlign: 'center',
          py: 1,
        }}>
          {placeholder}
        </Typography>
      ) : (
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
          {fields.map((field, index) => (
            <Chip
              key={`${field}-${index}`}
              label={field}
              color={color}
              variant="filled"
              size="small"
              icon={getFieldIcon(field) as React.ReactElement}
              onDelete={() => handleRemoveField(field)}
              deleteIcon={
                <Tooltip title="移除字段">
                  <CloseIcon />
                </Tooltip>
              }
              sx={{
                '& .MuiChip-label': {
                  maxWidth: 150,
                },
                '& .MuiChip-deleteIcon': {
                  '&:hover': {
                    color: 'error.main',
                  },
                },
              }}
            />
          ))}
        </Box>
      )}
    </Paper>
  )
}