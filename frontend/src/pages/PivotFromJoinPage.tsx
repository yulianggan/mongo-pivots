import React, { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Box,
  Typography,
  Card,
  CardContent,
  CardHeader,
  Button,
  Alert,
  Grid,
  Chip,
  CircularProgress,
  Breadcrumbs,
  Link,
  Fab,
} from '@mui/material'
import {
  ArrowBack as BackIcon,
  Assessment as PivotIcon,
  Warning as WarningIcon,
  CheckCircle as SuccessIcon,
} from '@mui/icons-material'
import { PivotLayout } from '@/components/pivot/PivotLayout'

interface JoinResultMetadata {
  result_id: string
  source_info: Array<{ name: string; type: string; records?: number }>
  join_statistics: {
    total_records: number
    matched_records: number
    execution_time_ms: number
    memory_peak_mb: number
  }
  quality_metrics: {
    completeness: number
    accuracy: number
    consistency: number
    uniqueness: number
  }
  created_at: string
  schema: {
    columns: string[]
    column_types: Record<string, string>
    row_count: number
  }
  pivot_recommendations: {
    recommended_dimensions: string[]
    recommended_measures: string[]
    performance_hints: string[]
  }
}

interface ValidationResult {
  result_id: string
  valid: boolean
  warnings: string[]
  recommendations: string[]
  performance_score: number
  data_summary: {
    total_rows: number
    total_columns: number
    numeric_columns: number
    estimated_memory_mb: number
  }
}

export const PivotFromJoinPage: React.FC = () => {
  const { resultId } = useParams<{ resultId: string }>()
  const navigate = useNavigate()
  
  const [metadata, setMetadata] = useState<JoinResultMetadata | null>(null)
  const [validation, setValidation] = useState<ValidationResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [pivotData, setPivotData] = useState<any[]>([])

  useEffect(() => {
    if (resultId) {
      loadJoinResultData()
    }
  }, [resultId])

  const loadJoinResultData = async () => {
    try {
      setLoading(true)
      setError(null)

      // 并行加载元数据和验证信息
      const [metadataResponse, validationResponse] = await Promise.all([
        fetch(`/api/pivot/result/${resultId}/metadata`),
        fetch(`/api/pivot/result/${resultId}/validate`)
      ])

      if (!metadataResponse.ok || !validationResponse.ok) {
        throw new Error('Failed to load join result data')
      }

      const metadataData = await metadataResponse.json()
      const validationData = await validationResponse.json()

      setMetadata(metadataData)
      setValidation(validationData)

      // 加载预览数据用于透视分析
      await loadPivotPreview()

    } catch (err) {
      console.error('Error loading join result:', err)
      setError(err instanceof Error ? err.message : '加载数据失败')
    } finally {
      setLoading(false)
    }
  }

  const loadPivotPreview = async () => {
    try {
      const response = await fetch(`/api/pivot/result/${resultId}/pivot-preview?limit=1000`)
      if (response.ok) {
        const data = await response.json()
        setPivotData(data.preview_data || [])
      }
    } catch (err) {
      console.error('Error loading pivot preview:', err)
      // 不阻断主流程，预览数据加载失败时使用空数组
      setPivotData([])
    }
  }

  const handleBackToQualityReport = () => {
    navigate(`/quality-report/${resultId}`)
  }

  const getQualityColor = (score: number) => {
    if (score >= 0.9) return 'success'
    if (score >= 0.7) return 'warning'
    return 'error'
  }

  const getPerformanceScoreColor = (score: number) => {
    if (score >= 80) return 'success'
    if (score >= 60) return 'warning'
    return 'error'
  }

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
        <Box textAlign="center">
          <CircularProgress size={60} />
          <Typography variant="h6" sx={{ mt: 2 }}>
            正在加载连接结果数据...
          </Typography>
        </Box>
      </Box>
    )
  }

  if (error) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="error" sx={{ mb: 2 }}>
          <Typography variant="h6" gutterBottom>
            数据加载失败
          </Typography>
          <Typography>{error}</Typography>
        </Alert>
        <Button variant="contained" onClick={() => navigate('/join-wizard')}>
          返回连接向导
        </Button>
      </Box>
    )
  }

  if (!metadata || !validation) {
    return (
      <Alert severity="error">
        未找到连接结果数据
      </Alert>
    )
  }

  return (
    <Box sx={{ p: 3 }}>
      {/* Header */}
      <Box mb={3}>
        <Breadcrumbs sx={{ mb: 1 }}>
          <Link
            component="button"
            variant="body2"
            onClick={() => navigate('/join-wizard')}
            sx={{ textDecoration: 'none' }}
          >
            连接向导
          </Link>
          <Link
            component="button"
            variant="body2"
            onClick={handleBackToQualityReport}
            sx={{ textDecoration: 'none' }}
          >
            质量报告
          </Link>
          <Typography variant="body2" color="text.primary">
            透视分析
          </Typography>
        </Breadcrumbs>
        
        <Box display="flex" alignItems="center" gap={2} mb={2}>
          <PivotIcon color="primary" fontSize="large" />
          <Typography variant="h4">
            透视分析
          </Typography>
          <Chip 
            label={`${metadata.schema.row_count.toLocaleString()} 行数据`} 
            color="primary" 
            variant="outlined" 
          />
        </Box>
        
        <Typography variant="body1" color="text.secondary">
          基于连接结果: {metadata.source_info.map(s => s.name).join(' + ')}
        </Typography>
      </Box>

      {/* Data Quality Summary */}
      <Card sx={{ mb: 3 }}>
        <CardHeader title="数据质量概览" />
        <CardContent>
          <Grid container spacing={3}>
            <Grid item xs={12} md={6}>
              <Typography variant="subtitle2" gutterBottom>
                质量指标
              </Typography>
              <Box display="flex" gap={2} flexWrap="wrap">
                <Chip 
                  label={`完整性: ${(metadata.quality_metrics.completeness * 100).toFixed(1)}%`}
                  color={getQualityColor(metadata.quality_metrics.completeness)}
                  size="small"
                />
                <Chip 
                  label={`准确性: ${(metadata.quality_metrics.accuracy * 100).toFixed(1)}%`}
                  color={getQualityColor(metadata.quality_metrics.accuracy)}
                  size="small"
                />
                <Chip 
                  label={`一致性: ${(metadata.quality_metrics.consistency * 100).toFixed(1)}%`}
                  color={getQualityColor(metadata.quality_metrics.consistency)}
                  size="small"
                />
                <Chip 
                  label={`唯一性: ${(metadata.quality_metrics.uniqueness * 100).toFixed(1)}%`}
                  color={getQualityColor(metadata.quality_metrics.uniqueness)}
                  size="small"
                />
              </Box>
            </Grid>

            <Grid item xs={12} md={6}>
              <Typography variant="subtitle2" gutterBottom>
                性能评分
              </Typography>
              <Box display="flex" alignItems="center" gap={2}>
                <Chip 
                  label={`${validation.performance_score.toFixed(0)}分`}
                  color={getPerformanceScoreColor(validation.performance_score)}
                  icon={validation.performance_score >= 80 ? <SuccessIcon /> : <WarningIcon />}
                />
                <Typography variant="body2" color="text.secondary">
                  预计内存使用: {validation.data_summary.estimated_memory_mb.toFixed(1)}MB
                </Typography>
              </Box>
            </Grid>
          </Grid>

          {validation.warnings.length > 0 && (
            <Alert severity="warning" sx={{ mt: 2 }}>
              <Typography variant="subtitle2" gutterBottom>
                注意事项
              </Typography>
              {validation.warnings.map((warning, index) => (
                <Typography key={index} variant="body2">
                  • {warning}
                </Typography>
              ))}
            </Alert>
          )}

          {validation.recommendations.length > 0 && (
            <Alert severity="info" sx={{ mt: 2 }}>
              <Typography variant="subtitle2" gutterBottom>
                优化建议
              </Typography>
              {validation.recommendations.map((recommendation, index) => (
                <Typography key={index} variant="body2">
                  • {recommendation}
                </Typography>
              ))}
            </Alert>
          )}
        </CardContent>
      </Card>

      {/* Recommended Fields */}
      <Card sx={{ mb: 3 }}>
        <CardHeader title="字段建议" />
        <CardContent>
          <Grid container spacing={3}>
            <Grid item xs={12} md={6}>
              <Typography variant="subtitle2" gutterBottom>
                推荐维度字段（用于分组）
              </Typography>
              <Box display="flex" gap={1} flexWrap="wrap">
                {metadata.pivot_recommendations.recommended_dimensions.map((field, index) => (
                  <Chip 
                    key={index} 
                    label={field} 
                    variant="outlined" 
                    color="primary"
                    size="small"
                  />
                ))}
              </Box>
            </Grid>

            <Grid item xs={12} md={6}>
              <Typography variant="subtitle2" gutterBottom>
                推荐度量字段（用于计算）
              </Typography>
              <Box display="flex" gap={1} flexWrap="wrap">
                {metadata.pivot_recommendations.recommended_measures.map((field, index) => (
                  <Chip 
                    key={index} 
                    label={field} 
                    variant="outlined" 
                    color="secondary"
                    size="small"
                  />
                ))}
              </Box>
            </Grid>
          </Grid>

          {metadata.pivot_recommendations.performance_hints.length > 0 && (
            <Alert severity="info" sx={{ mt: 2 }}>
              <Typography variant="subtitle2" gutterBottom>
                性能提示
              </Typography>
              {metadata.pivot_recommendations.performance_hints.map((hint, index) => (
                <Typography key={index} variant="body2">
                  • {hint}
                </Typography>
              ))}
            </Alert>
          )}
        </CardContent>
      </Card>

      {/* Pivot Analysis */}
      <Card>
        <CardHeader 
          title="透视分析配置"
          subheader="拖拽字段到相应区域开始分析"
        />
        <CardContent>
          <PivotLayout 
            data={pivotData}
            availableFields={metadata.schema.columns}
            fieldTypes={metadata.schema.column_types}
            onPivotUpdate={(pivotResult) => {
              console.log('Pivot updated:', pivotResult)
            }}
          />
        </CardContent>
      </Card>

      {/* Back to Quality Report FAB */}
      <Fab
        color="primary"
        aria-label="返回质量报告"
        sx={{
          position: 'fixed',
          bottom: 16,
          left: 16,
        }}
        onClick={handleBackToQualityReport}
      >
        <BackIcon />
      </Fab>
    </Box>
  )
}