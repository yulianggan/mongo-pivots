import React, { useState } from 'react'
import {
  Box,
  Typography,
  Grid,
  Card,
  CardContent,
  CardHeader,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  Alert,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Button,
  IconButton,
  Tooltip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
} from '@mui/material'
import {
  ExpandMore as ExpandMoreIcon,
  Error as ErrorIcon,
  Warning as WarningIcon,
  Info as InfoIcon,
  Visibility as ViewIcon,
  Build as FixIcon,
  Download as DownloadIcon,
} from '@mui/icons-material'

interface Anomaly {
  type: string
  field: string
  count: number
  severity: 'low' | 'medium' | 'high'
}

interface AnomalyDetectionPanelProps {
  anomalies: Anomaly[]
  totalRecords: number
}

interface AnomalyDetail {
  id: string
  type: string
  field: string
  severity: 'low' | 'medium' | 'high'
  count: number
  percentage: number
  description: string
  examples: string[]
  recommendation: string
  impact: string
}

export const AnomalyDetectionPanel: React.FC<AnomalyDetectionPanelProps> = ({
  anomalies,
  totalRecords,
}) => {
  const [selectedAnomaly, setSelectedAnomaly] = useState<AnomalyDetail | null>(null)
  const [detailDialogOpen, setDetailDialogOpen] = useState(false)

  const getSeverityColor = (severity: 'low' | 'medium' | 'high') => {
    switch (severity) {
      case 'high':
        return 'error'
      case 'medium':
        return 'warning'
      case 'low':
        return 'info'
      default:
        return 'default'
    }
  }

  const getSeverityIcon = (severity: 'low' | 'medium' | 'high') => {
    switch (severity) {
      case 'high':
        return <ErrorIcon />
      case 'medium':
        return <WarningIcon />
      case 'low':
        return <InfoIcon />
      default:
        return <InfoIcon />
    }
  }

  const getSeverityText = (severity: 'low' | 'medium' | 'high') => {
    switch (severity) {
      case 'high':
        return '高'
      case 'medium':
        return '中'
      case 'low':
        return '低'
      default:
        return '未知'
    }
  }

  const getAnomalyTypeText = (type: string) => {
    switch (type) {
      case 'missing_values':
        return '缺失值'
      case 'duplicate_records':
        return '重复记录'
      case 'format_inconsistency':
        return '格式不一致'
      case 'outlier_values':
        return '异常值'
      case 'referential_integrity':
        return '引用完整性'
      default:
        return type
    }
  }

  // Expand anomaly data with detailed information
  const anomalyDetails: AnomalyDetail[] = anomalies.map((anomaly, index) => ({
    id: `anomaly_${index}`,
    ...anomaly,
    percentage: (anomaly.count / totalRecords) * 100,
    description: getAnomalyDescription(anomaly.type, anomaly.field),
    examples: getAnomalyExamples(anomaly.type, anomaly.field),
    recommendation: getAnomalyRecommendation(anomaly.type),
    impact: getAnomalyImpact(anomaly.type, anomaly.severity),
  }))

  function getAnomalyDescription(type: string, field: string): string {
    switch (type) {
      case 'missing_values':
        return `字段 "${field}" 存在缺失值，影响数据完整性分析`
      case 'duplicate_records':
        return `字段 "${field}" 存在重复值，可能影响唯一性约束`
      case 'format_inconsistency':
        return `字段 "${field}" 格式不一致，可能影响数据处理和分析`
      default:
        return `字段 "${field}" 检测到数据质量问题`
    }
  }

  function getAnomalyExamples(type: string, field: string): string[] {
    switch (type) {
      case 'missing_values':
        return ['NULL', '空字符串', '未填写']
      case 'duplicate_records':
        return ['customer_id: C001 (重复3次)', 'customer_id: C045 (重复2次)']
      case 'format_inconsistency':
        return ['2023-01-15', '01/15/2023', '2023年1月15日']
      default:
        return ['示例数据不可用']
    }
  }

  function getAnomalyRecommendation(type: string): string {
    switch (type) {
      case 'missing_values':
        return '1. 添加数据验证规则\n2. 设置默认值或必填约束\n3. 完善数据收集流程'
      case 'duplicate_records':
        return '1. 建立主键约束\n2. 数据去重处理\n3. 增加唯一性检查'
      case 'format_inconsistency':
        return '1. 统一数据格式标准\n2. 添加格式验证\n3. 数据标准化处理'
      default:
        return '请联系数据管理员进行详细分析'
    }
  }

  function getAnomalyImpact(type: string, severity: 'low' | 'medium' | 'high'): string {
    const baseImpact = {
      'missing_values': '可能导致分析结果偏差，影响报表准确性',
      'duplicate_records': '影响统计准确性，可能导致重复计算',
      'format_inconsistency': '影响数据处理效率，可能导致解析错误',
    }[type] || '可能影响数据质量和分析结果'

    const severityImpact = {
      high: '严重影响业务决策',
      medium: '中等影响，建议及时处理',
      low: '轻微影响，建议定期处理',
    }[severity]

    return `${baseImpact}。${severityImpact}。`
  }

  const handleViewDetail = (anomaly: AnomalyDetail) => {
    setSelectedAnomaly(anomaly)
    setDetailDialogOpen(true)
  }

  const handleCloseDetail = () => {
    setDetailDialogOpen(false)
    setSelectedAnomaly(null)
  }

  const handleDownloadReport = () => {
    // Mock download functionality
    console.log('Downloading anomaly report...')
  }

  // Group anomalies by severity
  const groupedAnomalies = {
    high: anomalyDetails.filter(a => a.severity === 'high'),
    medium: anomalyDetails.filter(a => a.severity === 'medium'),
    low: anomalyDetails.filter(a => a.severity === 'low'),
  }

  return (
    <Box>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h6">
          异常检测结果
        </Typography>
        <Button
          startIcon={<DownloadIcon />}
          variant="outlined"
          onClick={handleDownloadReport}
        >
          导出报告
        </Button>
      </Box>
      
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        自动检测数据中的异常模式和质量问题，按严重程度分类显示。
      </Typography>

      {anomalyDetails.length === 0 ? (
        <Alert severity="success">
          恭喜！未检测到数据质量异常，您的数据质量良好。
        </Alert>
      ) : (
        <>
          {/* Summary Cards */}
          <Grid container spacing={3} sx={{ mb: 3 }}>
            <Grid item xs={12} md={4}>
              <Card>
                <CardContent>
                  <Box display="flex" alignItems="center" gap={2}>
                    <ErrorIcon color="error" />
                    <Box>
                      <Typography variant="h4" color="error.main">
                        {groupedAnomalies.high.length}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        高优先级问题
                      </Typography>
                    </Box>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
            
            <Grid item xs={12} md={4}>
              <Card>
                <CardContent>
                  <Box display="flex" alignItems="center" gap={2}>
                    <WarningIcon color="warning" />
                    <Box>
                      <Typography variant="h4" color="warning.main">
                        {groupedAnomalies.medium.length}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        中优先级问题
                      </Typography>
                    </Box>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
            
            <Grid item xs={12} md={4}>
              <Card>
                <CardContent>
                  <Box display="flex" alignItems="center" gap={2}>
                    <InfoIcon color="info" />
                    <Box>
                      <Typography variant="h4" color="info.main">
                        {groupedAnomalies.low.length}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        低优先级问题
                      </Typography>
                    </Box>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          </Grid>

          {/* Anomaly Details */}
          <Card>
            <CardHeader title="异常详情列表" />
            <CardContent>
              <TableContainer component={Paper} variant="outlined">
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableCell>异常类型</TableCell>
                      <TableCell>字段</TableCell>
                      <TableCell align="center">严重程度</TableCell>
                      <TableCell align="right">影响记录数</TableCell>
                      <TableCell align="right">影响比例</TableCell>
                      <TableCell align="center">操作</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {anomalyDetails
                      .sort((a, b) => {
                        const severityOrder = { high: 3, medium: 2, low: 1 }
                        return severityOrder[b.severity] - severityOrder[a.severity]
                      })
                      .map((anomaly) => (
                        <TableRow key={anomaly.id}>
                          <TableCell>
                            <Box display="flex" alignItems="center" gap={1}>
                              {getSeverityIcon(anomaly.severity)}
                              <Typography variant="body2">
                                {getAnomalyTypeText(anomaly.type)}
                              </Typography>
                            </Box>
                          </TableCell>
                          <TableCell>
                            <Typography variant="body2" fontFamily="monospace">
                              {anomaly.field}
                            </Typography>
                          </TableCell>
                          <TableCell align="center">
                            <Chip
                              label={getSeverityText(anomaly.severity)}
                              color={getSeverityColor(anomaly.severity)}
                              size="small"
                            />
                          </TableCell>
                          <TableCell align="right">
                            <Typography variant="body2">
                              {anomaly.count.toLocaleString()}
                            </Typography>
                          </TableCell>
                          <TableCell align="right">
                            <Typography variant="body2">
                              {anomaly.percentage.toFixed(2)}%
                            </Typography>
                          </TableCell>
                          <TableCell align="center">
                            <Tooltip title="查看详情">
                              <IconButton
                                size="small"
                                onClick={() => handleViewDetail(anomaly)}
                              >
                                <ViewIcon />
                              </IconButton>
                            </Tooltip>
                          </TableCell>
                        </TableRow>
                      ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>

          {/* Recommendations */}
          <Card sx={{ mt: 3 }}>
            <CardHeader title="修复建议" />
            <CardContent>
              {Object.entries(groupedAnomalies).map(([severity, items]) => 
                items.length > 0 && (
                  <Accordion key={severity}>
                    <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                      <Box display="flex" alignItems="center" gap={2}>
                        {getSeverityIcon(severity as any)}
                        <Typography variant="subtitle1">
                          {getSeverityText(severity as any)}优先级问题 ({items.length}个)
                        </Typography>
                      </Box>
                    </AccordionSummary>
                    <AccordionDetails>
                      <List>
                        {items.map((item) => (
                          <ListItem key={item.id}>
                            <ListItemIcon>
                              <FixIcon color="primary" />
                            </ListItemIcon>
                            <ListItemText
                              primary={`${getAnomalyTypeText(item.type)} - ${item.field}`}
                              secondary={item.recommendation.split('\n').map((line, index) => (
                                <div key={index}>{line}</div>
                              ))}
                            />
                          </ListItem>
                        ))}
                      </List>
                    </AccordionDetails>
                  </Accordion>
                )
              )}
            </CardContent>
          </Card>
        </>
      )}

      {/* Detail Dialog */}
      <Dialog
        open={detailDialogOpen}
        onClose={handleCloseDetail}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          异常详情 - {selectedAnomaly && getAnomalyTypeText(selectedAnomaly.type)}
        </DialogTitle>
        <DialogContent>
          {selectedAnomaly && (
            <Grid container spacing={3}>
              <Grid item xs={12} md={6}>
                <Typography variant="subtitle2" gutterBottom>
                  基本信息
                </Typography>
                <Box display="flex" flexDirection="column" gap={2}>
                  <Box>
                    <Typography variant="body2" color="text.secondary">
                      字段名称
                    </Typography>
                    <Typography variant="body1" fontFamily="monospace">
                      {selectedAnomaly.field}
                    </Typography>
                  </Box>
                  <Box>
                    <Typography variant="body2" color="text.secondary">
                      严重程度
                    </Typography>
                    <Chip
                      label={getSeverityText(selectedAnomaly.severity)}
                      color={getSeverityColor(selectedAnomaly.severity)}
                      size="small"
                    />
                  </Box>
                  <Box>
                    <Typography variant="body2" color="text.secondary">
                      影响范围
                    </Typography>
                    <Typography variant="body1">
                      {selectedAnomaly.count.toLocaleString()} 条记录 ({selectedAnomaly.percentage.toFixed(2)}%)
                    </Typography>
                  </Box>
                </Box>
              </Grid>

              <Grid item xs={12} md={6}>
                <Typography variant="subtitle2" gutterBottom>
                  异常示例
                </Typography>
                <List dense>
                  {selectedAnomaly.examples.map((example, index) => (
                    <ListItem key={index}>
                      <ListItemText>
                        <Typography variant="body2" fontFamily="monospace" color="text.secondary">
                          {example}
                        </Typography>
                      </ListItemText>
                    </ListItem>
                  ))}
                </List>
              </Grid>

              <Grid item xs={12}>
                <Typography variant="subtitle2" gutterBottom>
                  问题描述
                </Typography>
                <Typography variant="body2" paragraph>
                  {selectedAnomaly.description}
                </Typography>

                <Typography variant="subtitle2" gutterBottom>
                  业务影响
                </Typography>
                <Typography variant="body2" paragraph>
                  {selectedAnomaly.impact}
                </Typography>

                <Typography variant="subtitle2" gutterBottom>
                  修复建议
                </Typography>
                <Box component="pre" sx={{ 
                  whiteSpace: 'pre-wrap', 
                  fontFamily: 'inherit',
                  fontSize: '0.875rem',
                  color: 'text.secondary',
                  m: 0,
                }}>
                  {selectedAnomaly.recommendation}
                </Box>
              </Grid>
            </Grid>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDetail}>
            关闭
          </Button>
          <Button variant="contained" startIcon={<FixIcon />}>
            生成修复脚本
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}