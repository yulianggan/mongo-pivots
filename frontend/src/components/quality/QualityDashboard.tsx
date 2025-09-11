import React, { useState, useEffect } from 'react'
import {
  Box,
  Typography,
  Grid,
  Card,
  CardContent,
  CardHeader,
  Tab,
  Tabs,
  Alert,
  Divider,
} from '@mui/material'
import {
  Assessment as AssessmentIcon,
  Timeline as TimelineIcon,
  Warning as WarningIcon,
  CheckCircle as CheckIcon,
} from '@mui/icons-material'
import { QualityMetricsCard } from './QualityMetricsCard'
import { DataDistributionChart } from './DataDistributionChart'
import { AnomalyDetectionPanel } from './AnomalyDetectionPanel'
import { QualityTrends } from './QualityTrends'

interface TabPanelProps {
  children?: React.ReactNode
  index: number
  value: number
}

const TabPanel: React.FC<TabPanelProps> = ({ children, value, index }) => (
  <div role="tabpanel" hidden={value !== index}>
    {value === index && <Box sx={{ pt: 3 }}>{children}</Box>}
  </div>
)

interface QualityReport {
  id: string
  name: string
  executionTime: string
  status: 'completed' | 'running' | 'failed'
  metrics: {
    totalRecords: number
    completeness: number
    accuracy: number
    consistency: number
    uniqueness: number
  }
  anomalies: Array<{
    type: string
    field: string
    count: number
    severity: 'low' | 'medium' | 'high'
  }>
}

interface QualityDashboardProps {
  reportId?: string
  onReportSelect?: (reportId: string) => void
}

export const QualityDashboard: React.FC<QualityDashboardProps> = ({
  reportId,
  onReportSelect,
}) => {
  const [currentTab, setCurrentTab] = useState(0)
  const [qualityReport, setQualityReport] = useState<QualityReport | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchQualityReport = async () => {
      setLoading(true)
      
      // Mock data for development
      const mockReport: QualityReport = {
        id: reportId || 'report_001',
        name: '客户订单数据连接质量报告',
        executionTime: new Date().toISOString(),
        status: 'completed',
        metrics: {
          totalRecords: 15847,
          completeness: 94.2,
          accuracy: 89.7,
          consistency: 91.8,
          uniqueness: 96.5,
        },
        anomalies: [
          {
            type: 'missing_values',
            field: 'customer.email',
            count: 234,
            severity: 'medium',
          },
          {
            type: 'duplicate_records',
            field: 'customer_id',
            count: 45,
            severity: 'high',
          },
          {
            type: 'format_inconsistency',
            field: 'order_date',
            count: 78,
            severity: 'low',
          },
        ],
      }
      
      setTimeout(() => {
        setQualityReport(mockReport)
        setLoading(false)
      }, 1000)
    }

    fetchQualityReport()
  }, [reportId])

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setCurrentTab(newValue)
  }

  const getOverallScore = (metrics: QualityReport['metrics']): number => {
    const { completeness, accuracy, consistency, uniqueness } = metrics
    return Math.round((completeness + accuracy + consistency + uniqueness) / 4)
  }

  const getStatusColor = (status: QualityReport['status']) => {
    switch (status) {
      case 'completed':
        return 'success'
      case 'running':
        return 'info'
      case 'failed':
        return 'error'
      default:
        return 'default'
    }
  }

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" height={400}>
        <Typography>加载质量报告中...</Typography>
      </Box>
    )
  }

  if (!qualityReport) {
    return (
      <Alert severity="error">
        无法加载质量报告数据
      </Alert>
    )
  }

  const overallScore = getOverallScore(qualityReport.metrics)

  return (
    <Box>
      {/* Report Header */}
      <Card sx={{ mb: 3 }}>
        <CardHeader
          title={
            <Box display="flex" alignItems="center" gap={2}>
              <AssessmentIcon color="primary" />
              <Typography variant="h5">
                {qualityReport.name}
              </Typography>
            </Box>
          }
          subheader={
            <Box display="flex" alignItems="center" gap={2} mt={1}>
              <Typography variant="body2" color="text.secondary">
                执行时间: {new Date(qualityReport.executionTime).toLocaleString()}
              </Typography>
              <Divider orientation="vertical" flexItem />
              <Typography variant="body2" color="text.secondary">
                总记录数: {qualityReport.metrics.totalRecords.toLocaleString()}
              </Typography>
              <Divider orientation="vertical" flexItem />
              <Box display="flex" alignItems="center" gap={1}>
                <CheckIcon color={getStatusColor(qualityReport.status)} fontSize="small" />
                <Typography 
                  variant="body2" 
                  color={`${getStatusColor(qualityReport.status)}.main`}
                >
                  {qualityReport.status === 'completed' ? '已完成' : 
                   qualityReport.status === 'running' ? '运行中' : '失败'}
                </Typography>
              </Box>
            </Box>
          }
        />
        <CardContent>
          <Box display="flex" alignItems="center" gap={3}>
            <Box textAlign="center">
              <Typography variant="h3" color="primary" fontWeight="bold">
                {overallScore}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                总体质量评分
              </Typography>
            </Box>
            <Divider orientation="vertical" flexItem />
            <Grid container spacing={2} sx={{ flex: 1 }}>
              <Grid item xs={3}>
                <Box textAlign="center">
                  <Typography variant="h6" color="success.main">
                    {qualityReport.metrics.completeness}%
                  </Typography>
                  <Typography variant="caption">完整性</Typography>
                </Box>
              </Grid>
              <Grid item xs={3}>
                <Box textAlign="center">
                  <Typography variant="h6" color="info.main">
                    {qualityReport.metrics.accuracy}%
                  </Typography>
                  <Typography variant="caption">准确性</Typography>
                </Box>
              </Grid>
              <Grid item xs={3}>
                <Box textAlign="center">
                  <Typography variant="h6" color="warning.main">
                    {qualityReport.metrics.consistency}%
                  </Typography>
                  <Typography variant="caption">一致性</Typography>
                </Box>
              </Grid>
              <Grid item xs={3}>
                <Box textAlign="center">
                  <Typography variant="h6" color="secondary.main">
                    {qualityReport.metrics.uniqueness}%
                  </Typography>
                  <Typography variant="caption">唯一性</Typography>
                </Box>
              </Grid>
            </Grid>
          </Box>
        </CardContent>
      </Card>

      {/* Anomaly Alert */}
      {qualityReport.anomalies.length > 0 && (
        <Alert 
          severity="warning" 
          sx={{ mb: 3 }}
          icon={<WarningIcon />}
        >
          <Typography variant="subtitle2" gutterBottom>
            检测到 {qualityReport.anomalies.length} 个数据质量问题
          </Typography>
          <Typography variant="body2">
            包括 {qualityReport.anomalies.filter(a => a.severity === 'high').length} 个高优先级问题，
            建议优先处理。点击异常检测标签页查看详情。
          </Typography>
        </Alert>
      )}

      {/* Tab Navigation */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs value={currentTab} onChange={handleTabChange}>
          <Tab label="质量指标" icon={<AssessmentIcon />} />
          <Tab label="数据分布" icon={<TimelineIcon />} />
          <Tab label="异常检测" icon={<WarningIcon />} />
          <Tab label="质量趋势" icon={<TimelineIcon />} />
        </Tabs>
      </Box>

      {/* Tab Panels */}
      <TabPanel value={currentTab} index={0}>
        <QualityMetricsCard 
          metrics={qualityReport.metrics}
          totalRecords={qualityReport.metrics.totalRecords}
        />
      </TabPanel>

      <TabPanel value={currentTab} index={1}>
        <DataDistributionChart 
          reportId={qualityReport.id}
          data={qualityReport}
        />
      </TabPanel>

      <TabPanel value={currentTab} index={2}>
        <AnomalyDetectionPanel 
          anomalies={qualityReport.anomalies}
          totalRecords={qualityReport.metrics.totalRecords}
        />
      </TabPanel>

      <TabPanel value={currentTab} index={3}>
        <QualityTrends reportId={qualityReport.id} />
      </TabPanel>
    </Box>
  )
}