import React, { useState, useEffect } from 'react'
import {
  Box,
  Typography,
  Card,
  CardContent,
  CardHeader,
  LinearProgress,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Chip,
  Alert,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Grid,
  Divider,
  Accordion,
  AccordionSummary,
  AccordionDetails,
} from '@mui/material'
import {
  PlayArrow as StartIcon,
  Pause as PauseIcon,
  Stop as StopIcon,
  CheckCircle as CompleteIcon,
  Error as ErrorIcon,
  Warning as WarningIcon,
  Info as InfoIcon,
  ExpandMore as ExpandMoreIcon,
  Refresh as RefreshIcon,
  Timeline as TimelineIcon,
} from '@mui/icons-material'

interface ProgressStep {
  id: string
  name: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped'
  progress: number
  startTime?: string
  endTime?: string
  duration?: number
  message?: string
  details?: string[]
  subSteps?: ProgressStep[]
}

interface ExecutionJob {
  id: string
  name: string
  type: 'join' | 'pivot' | 'analysis'
  status: 'running' | 'completed' | 'failed' | 'paused'
  overallProgress: number
  startTime: string
  estimatedEndTime?: string
  steps: ProgressStep[]
  metadata: {
    dataSourcesCount: number
    expectedRecords: number
    processedRecords: number
    errorCount: number
  }
}

interface ProgressTrackerProps {
  jobId: string
  onJobComplete?: (jobId: string, result: any) => void
  onJobFailed?: (jobId: string, error: any) => void
}

export const ProgressTracker: React.FC<ProgressTrackerProps> = ({
  jobId,
  onJobComplete,
  onJobFailed,
}) => {
  const [job, setJob] = useState<ExecutionJob | null>(null)
  const [isExpanded, setIsExpanded] = useState(true)
  const [showDetails, setShowDetails] = useState(false)
  const [autoRefresh, setAutoRefresh] = useState(true)

  useEffect(() => {
    // Initialize with mock job data
    const mockJob: ExecutionJob = {
      id: jobId,
      name: '客户订单数据连接任务',
      type: 'join',
      status: 'running',
      overallProgress: 45,
      startTime: new Date(Date.now() - 300000).toISOString(), // Started 5 minutes ago
      estimatedEndTime: new Date(Date.now() + 420000).toISOString(), // Estimated to complete in 7 minutes
      steps: [
        {
          id: 'validation',
          name: '数据源验证',
          status: 'completed',
          progress: 100,
          startTime: new Date(Date.now() - 300000).toISOString(),
          endTime: new Date(Date.now() - 240000).toISOString(),
          duration: 60,
          message: '数据源验证完成',
          details: ['检查数据源连接状态', '验证字段结构', '确认数据权限'],
        },
        {
          id: 'preprocessing',
          name: '数据预处理',
          status: 'completed',
          progress: 100,
          startTime: new Date(Date.now() - 240000).toISOString(),
          endTime: new Date(Date.now() - 120000).toISOString(),
          duration: 120,
          message: '数据预处理完成',
          details: ['数据类型转换', '缺失值处理', '重复数据清理'],
          subSteps: [
            { id: 'transform', name: '数据转换', status: 'completed', progress: 100 },
            { id: 'clean', name: '数据清理', status: 'completed', progress: 100 },
            { id: 'validate', name: '质量验证', status: 'completed', progress: 100 },
          ],
        },
        {
          id: 'joining',
          name: '数据连接',
          status: 'running',
          progress: 65,
          startTime: new Date(Date.now() - 120000).toISOString(),
          message: '正在执行数据连接操作...',
          details: ['处理中的记录: 8,234 / 12,847', '当前连接策略: Inner Join', '预计剩余时间: 3分钟'],
          subSteps: [
            { id: 'index', name: '创建索引', status: 'completed', progress: 100 },
            { id: 'match', name: '记录匹配', status: 'running', progress: 65 },
            { id: 'merge', name: '数据合并', status: 'pending', progress: 0 },
          ],
        },
        {
          id: 'quality_check',
          name: '质量检查',
          status: 'pending',
          progress: 0,
          message: '等待数据连接完成',
          details: ['数据完整性检查', '异常值检测', '质量报告生成'],
        },
        {
          id: 'output',
          name: '结果输出',
          status: 'pending',
          progress: 0,
          message: '等待质量检查完成',
          details: ['生成输出文件', '保存到数据库', '发送完成通知'],
        },
      ],
      metadata: {
        dataSourcesCount: 2,
        expectedRecords: 12847,
        processedRecords: 8234,
        errorCount: 12,
      },
    }

    setJob(mockJob)

    // Simulate progress updates
    let interval: NodeJS.Timeout
    if (autoRefresh && mockJob.status === 'running') {
      interval = setInterval(() => {
        setJob(prev => {
          if (!prev || prev.status !== 'running') return prev

          // Update progress
          const newJob = { ...prev }
          const runningStep = newJob.steps.find(s => s.status === 'running')
          
          if (runningStep) {
            runningStep.progress = Math.min(runningStep.progress + Math.random() * 5, 100)
            
            if (runningStep.progress >= 100) {
              runningStep.status = 'completed'
              runningStep.endTime = new Date().toISOString()
              runningStep.duration = Math.floor((new Date().getTime() - new Date(runningStep.startTime!).getTime()) / 1000)
              runningStep.message = `${runningStep.name}完成`
              
              // Start next step
              const currentIndex = newJob.steps.findIndex(s => s.id === runningStep.id)
              if (currentIndex < newJob.steps.length - 1) {
                const nextStep = newJob.steps[currentIndex + 1]
                nextStep.status = 'running'
                nextStep.startTime = new Date().toISOString()
                nextStep.message = `正在执行${nextStep.name}...`
              } else {
                // All steps completed
                newJob.status = 'completed'
                newJob.overallProgress = 100
                onJobComplete?.(newJob.id, { status: 'success' })
              }
            }
          }

          // Update overall progress
          const completedSteps = newJob.steps.filter(s => s.status === 'completed').length
          const totalSteps = newJob.steps.length
          const runningStepProgress = runningStep ? runningStep.progress : 0
          
          newJob.overallProgress = Math.min(
            ((completedSteps + runningStepProgress / 100) / totalSteps) * 100,
            100
          )

          // Update processed records
          newJob.metadata.processedRecords = Math.min(
            newJob.metadata.processedRecords + Math.floor(Math.random() * 50),
            newJob.metadata.expectedRecords
          )

          return newJob
        })
      }, 2000)
    }

    return () => {
      if (interval) clearInterval(interval)
    }
  }, [jobId, autoRefresh, onJobComplete])

  const getStatusIcon = (status: ProgressStep['status']) => {
    switch (status) {
      case 'completed':
        return <CompleteIcon color="success" />
      case 'running':
        return <StartIcon color="primary" />
      case 'failed':
        return <ErrorIcon color="error" />
      case 'pending':
        return <InfoIcon color="disabled" />
      case 'skipped':
        return <WarningIcon color="warning" />
      default:
        return <InfoIcon />
    }
  }

  const getStatusColor = (status: ProgressStep['status']) => {
    switch (status) {
      case 'completed':
        return 'success'
      case 'running':
        return 'primary'
      case 'failed':
        return 'error'
      case 'pending':
        return 'default'
      case 'skipped':
        return 'warning'
      default:
        return 'default'
    }
  }

  const getStatusText = (status: ProgressStep['status']) => {
    switch (status) {
      case 'completed':
        return '已完成'
      case 'running':
        return '进行中'
      case 'failed':
        return '失败'
      case 'pending':
        return '等待中'
      case 'skipped':
        return '已跳过'
      default:
        return '未知'
    }
  }

  const formatDuration = (seconds: number) => {
    const minutes = Math.floor(seconds / 60)
    const remainingSeconds = seconds % 60
    return `${minutes}分${remainingSeconds}秒`
  }

  const handlePauseResume = () => {
    if (!job) return
    
    const newStatus = job.status === 'running' ? 'paused' : 'running'
    setJob(prev => prev ? { ...prev, status: newStatus } : null)
    setAutoRefresh(newStatus === 'running')
  }

  const handleStop = () => {
    if (!job) return
    
    setJob(prev => prev ? { ...prev, status: 'failed' } : null)
    setAutoRefresh(false)
    onJobFailed?.(job.id, { reason: 'User stopped' })
  }

  const handleRefresh = () => {
    // Trigger manual refresh
    setAutoRefresh(true)
    setTimeout(() => setAutoRefresh(job?.status === 'running'), 1000)
  }

  if (!job) {
    return (
      <Alert severity="info">
        加载执行任务信息...
      </Alert>
    )
  }

  return (
    <Box>
      {/* Job Header */}
      <Card sx={{ mb: 3 }}>
        <CardHeader
          title={
            <Box display="flex" alignItems="center" gap={2}>
              <TimelineIcon color="primary" />
              <Typography variant="h6">
                {job.name}
              </Typography>
              <Chip 
                label={job.status === 'running' ? '运行中' : 
                       job.status === 'completed' ? '已完成' :
                       job.status === 'failed' ? '失败' : '暂停'}
                color={getStatusColor(job.status) as any}
                size="small"
              />
            </Box>
          }
          action={
            <Box display="flex" gap={1}>
              <Button
                size="small"
                onClick={handleRefresh}
                startIcon={<RefreshIcon />}
              >
                刷新
              </Button>
              <Button
                size="small"
                onClick={handlePauseResume}
                startIcon={job.status === 'running' ? <PauseIcon /> : <StartIcon />}
                disabled={job.status === 'completed' || job.status === 'failed'}
              >
                {job.status === 'running' ? '暂停' : '继续'}
              </Button>
              <Button
                size="small"
                onClick={handleStop}
                startIcon={<StopIcon />}
                color="error"
                disabled={job.status === 'completed' || job.status === 'failed'}
              >
                停止
              </Button>
            </Box>
          }
        />
        <CardContent>
          <Grid container spacing={3}>
            <Grid item xs={12} md={8}>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                总体进度
              </Typography>
              <Box display="flex" alignItems="center" gap={2} mb={2}>
                <LinearProgress 
                  variant="determinate" 
                  value={job.overallProgress} 
                  sx={{ flex: 1, height: 8, borderRadius: 4 }}
                />
                <Typography variant="body2" fontWeight="bold">
                  {job.overallProgress.toFixed(1)}%
                </Typography>
              </Box>

              <Typography variant="body2" color="text.secondary">
                开始时间: {new Date(job.startTime).toLocaleString()} | 
                {job.estimatedEndTime && ` 预计完成: ${new Date(job.estimatedEndTime).toLocaleString()}`}
              </Typography>
            </Grid>

            <Grid item xs={12} md={4}>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                处理统计
              </Typography>
              <Box display="flex" flexDirection="column" gap={1}>
                <Typography variant="body2">
                  数据源: {job.metadata.dataSourcesCount} 个
                </Typography>
                <Typography variant="body2">
                  处理进度: {job.metadata.processedRecords.toLocaleString()} / {job.metadata.expectedRecords.toLocaleString()}
                </Typography>
                <Typography variant="body2" color="error.main">
                  错误数: {job.metadata.errorCount}
                </Typography>
              </Box>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {/* Step Details */}
      <Card>
        <CardHeader 
          title="执行步骤"
          action={
            <Button 
              size="small" 
              onClick={() => setShowDetails(!showDetails)}
            >
              {showDetails ? '简化视图' : '详细信息'}
            </Button>
          }
        />
        <CardContent>
          <List>
            {job.steps.map((step, index) => (
              <React.Fragment key={step.id}>
                <ListItem>
                  <ListItemIcon>
                    {getStatusIcon(step.status)}
                  </ListItemIcon>
                  <ListItemText>
                    <Box>
                      <Box display="flex" alignItems="center" gap={2} mb={1}>
                        <Typography variant="subtitle1">
                          {step.name}
                        </Typography>
                        <Chip 
                          label={getStatusText(step.status)} 
                          color={getStatusColor(step.status) as any}
                          size="small"
                        />
                        {step.duration && (
                          <Typography variant="body2" color="text.secondary">
                            耗时: {formatDuration(step.duration)}
                          </Typography>
                        )}
                      </Box>

                      {step.status !== 'pending' && (
                        <LinearProgress 
                          variant="determinate" 
                          value={step.progress} 
                          sx={{ mb: 1, height: 4 }}
                          color={getStatusColor(step.status) as any}
                        />
                      )}

                      {step.message && (
                        <Typography variant="body2" color="text.secondary">
                          {step.message}
                        </Typography>
                      )}

                      {showDetails && step.details && (
                        <Box mt={1}>
                          {step.details.map((detail, detailIndex) => (
                            <Typography 
                              key={detailIndex} 
                              variant="caption" 
                              display="block" 
                              color="text.secondary"
                            >
                              • {detail}
                            </Typography>
                          ))}
                        </Box>
                      )}

                      {showDetails && step.subSteps && step.subSteps.length > 0 && (
                        <Accordion sx={{ mt: 1 }}>
                          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                            <Typography variant="body2">
                              子步骤 ({step.subSteps.length})
                            </Typography>
                          </AccordionSummary>
                          <AccordionDetails>
                            <List dense>
                              {step.subSteps.map(subStep => (
                                <ListItem key={subStep.id}>
                                  <ListItemIcon sx={{ minWidth: 32 }}>
                                    {getStatusIcon(subStep.status)}
                                  </ListItemIcon>
                                  <ListItemText>
                                    <Typography variant="body2">
                                      {subStep.name}
                                    </Typography>
                                    {subStep.status !== 'pending' && (
                                      <LinearProgress 
                                        variant="determinate" 
                                        value={subStep.progress} 
                                        size="small"
                                        sx={{ mt: 0.5, height: 2 }}
                                      />
                                    )}
                                  </ListItemText>
                                </ListItem>
                              ))}
                            </List>
                          </AccordionDetails>
                        </Accordion>
                      )}
                    </Box>
                  </ListItemText>
                </ListItem>
                {index < job.steps.length - 1 && <Divider />}
              </React.Fragment>
            ))}
          </List>
        </CardContent>
      </Card>

      {/* Error Details Dialog */}
      <Dialog
        open={job.status === 'failed'}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>执行失败</DialogTitle>
        <DialogContent>
          <Alert severity="error" sx={{ mb: 2 }}>
            任务执行过程中发生错误，请查看详细信息并重试。
          </Alert>
          <Typography variant="body2">
            失败步骤: {job.steps.find(s => s.status === 'failed')?.name || '未知'}
          </Typography>
          <Typography variant="body2">
            错误时间: {new Date().toLocaleString()}
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setJob(prev => prev ? { ...prev, status: 'paused' } : null)}>
            关闭
          </Button>
          <Button variant="contained" color="primary">
            重试
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}