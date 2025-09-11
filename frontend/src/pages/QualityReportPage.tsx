import React, { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Box,
  Typography,
  Breadcrumbs,
  Link,
  Alert,
  Fab,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  ListItemIcon,
  Divider,
} from '@mui/material'
import {
  ArrowBack as BackIcon,
  Assessment as ReportIcon,
  Timeline as TrendIcon,
  Share as ShareIcon,
  Analytics as PivotIcon,
} from '@mui/icons-material'
import { QualityDashboard } from '@/components/quality/QualityDashboard'
import { ProgressTracker } from '@/components/progress/ProgressTracker'

interface QualityReportPageProps {}

interface ReportSummary {
  id: string
  name: string
  executionTime: string
  status: 'completed' | 'running' | 'failed'
  overallScore: number
}

export const QualityReportPage: React.FC<QualityReportPageProps> = () => {
  const { reportId } = useParams<{ reportId: string }>()
  const navigate = useNavigate()
  const [showReportList, setShowReportList] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [currentReport, setCurrentReport] = useState<string | undefined>(reportId)

  // Mock report list
  const availableReports: ReportSummary[] = [
    {
      id: 'report_001',
      name: '客户订单数据连接质量报告',
      executionTime: new Date(Date.now() - 3600000).toISOString(),
      status: 'completed',
      overallScore: 92.3,
    },
    {
      id: 'report_002',
      name: '产品库存数据分析报告',
      executionTime: new Date(Date.now() - 7200000).toISOString(),
      status: 'completed',
      overallScore: 87.6,
    },
    {
      id: 'report_003',
      name: '用户行为数据质量检查',
      executionTime: new Date(Date.now() - 1800000).toISOString(),
      status: 'running',
      overallScore: 0,
    },
  ]

  const handleBackToWizard = () => {
    navigate('/join-wizard')
  }

  const handleReportSelect = (newReportId: string) => {
    setCurrentReport(newReportId)
    navigate(`/quality-report/${newReportId}`)
    setShowReportList(false)
  }

  const handleJobComplete = (jobId: string, result: any) => {
    // Handle job completion - could navigate to results or show success message
    console.log('Job completed:', jobId, result)
  }

  const handleJobFailed = (jobId: string, error: any) => {
    // Handle job failure - could show error message or retry options
    console.log('Job failed:', jobId, error)
  }

  const handleStartPivotAnalysis = () => {
    if (currentReport) {
      navigate(`/pivot-from-join/${currentReport}`)
    }
  }

  const getStatusColor = (status: ReportSummary['status']) => {
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

  const getStatusText = (status: ReportSummary['status']) => {
    switch (status) {
      case 'completed':
        return '已完成'
      case 'running':
        return '运行中'
      case 'failed':
        return '失败'
      default:
        return '未知'
    }
  }

  // Show progress tracker if report is currently running
  const currentReportData = availableReports.find(r => r.id === currentReport)
  const isRunning = currentReportData?.status === 'running'

  return (
    <Box sx={{ p: 3 }}>
      {/* Header */}
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Box>
          <Breadcrumbs sx={{ mb: 1 }}>
            <Link
              component="button"
              variant="body2"
              onClick={handleBackToWizard}
              sx={{ textDecoration: 'none' }}
            >
              连接向导
            </Link>
            <Typography variant="body2" color="text.primary">
              质量报告
            </Typography>
          </Breadcrumbs>
          
          <Typography variant="h4" gutterBottom>
            数据质量报告
          </Typography>
          
          <Typography variant="body1" color="text.secondary">
            {currentReportData ? currentReportData.name : '质量分析结果展示'}
          </Typography>
        </Box>

        <Box display="flex" gap={2}>
          {currentReportData?.status === 'completed' && (
            <Button
              variant="contained"
              startIcon={<PivotIcon />}
              onClick={handleStartPivotAnalysis}
              sx={{ mr: 1 }}
            >
              开始透视分析
            </Button>
          )}
          
          <Button
            variant="outlined"
            startIcon={<ReportIcon />}
            onClick={() => setShowReportList(true)}
          >
            切换报告
          </Button>
          
          <Button
            variant="outlined"
            startIcon={<ShareIcon />}
            onClick={() => {
              // Mock share functionality
              navigator.clipboard?.writeText(window.location.href)
              alert('报告链接已复制到剪贴板')
            }}
          >
            分享报告
          </Button>
        </Box>
      </Box>

      {/* Content */}
      {isLoading ? (
        <Alert severity="info">
          正在加载质量报告数据...
        </Alert>
      ) : isRunning ? (
        <Box>
          <Alert severity="info" sx={{ mb: 3 }}>
            数据处理正在进行中，质量报告将在处理完成后生成。您可以在此页面实时跟踪处理进度。
          </Alert>
          
          <ProgressTracker 
            jobId={currentReport || 'default'}
            onJobComplete={handleJobComplete}
            onJobFailed={handleJobFailed}
          />
        </Box>
      ) : (
        <QualityDashboard 
          reportId={currentReport}
          onReportSelect={handleReportSelect}
        />
      )}

      {/* Back to Wizard FAB */}
      <Fab
        color="primary"
        aria-label="返回向导"
        sx={{
          position: 'fixed',
          bottom: 16,
          left: 16,
        }}
        onClick={handleBackToWizard}
      >
        <BackIcon />
      </Fab>

      {/* Report List Dialog */}
      <Dialog
        open={showReportList}
        onClose={() => setShowReportList(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          选择质量报告
        </DialogTitle>
        <DialogContent>
          <List>
            {availableReports.map((report, index) => (
              <React.Fragment key={report.id}>
                <ListItem disablePadding>
                  <ListItemButton 
                    onClick={() => handleReportSelect(report.id)}
                    selected={currentReport === report.id}
                  >
                    <ListItemIcon>
                      <ReportIcon color={getStatusColor(report.status) as any} />
                    </ListItemIcon>
                    <ListItemText
                      primary={report.name}
                      secondary={
                        <Box>
                          <Typography variant="body2" color="text.secondary">
                            执行时间: {new Date(report.executionTime).toLocaleString()}
                          </Typography>
                          <Box display="flex" alignItems="center" gap={2} mt={0.5}>
                            <Typography 
                              variant="caption" 
                              color={`${getStatusColor(report.status)}.main`}
                            >
                              {getStatusText(report.status)}
                            </Typography>
                            {report.status === 'completed' && (
                              <Typography variant="caption" color="text.secondary">
                                质量评分: {report.overallScore.toFixed(1)}
                              </Typography>
                            )}
                          </Box>
                        </Box>
                      }
                    />
                  </ListItemButton>
                </ListItem>
                {index < availableReports.length - 1 && <Divider />}
              </React.Fragment>
            ))}
          </List>
          
          {availableReports.length === 0 && (
            <Alert severity="info">
              暂无可用的质量报告。请先通过连接向导执行数据处理任务。
            </Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowReportList(false)}>
            取消
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}