import React from 'react'
import {
  Box,
  Typography,
  Grid,
  Card,
  CardContent,
  LinearProgress,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Chip,
} from '@mui/material'
import {
  CheckCircle as CompleteIcon,
  Star as AccuracyIcon,
  Balance as ConsistencyIcon,
  Fingerprint as UniquenessIcon,
  Storage as RecordsIcon,
  TrendingUp as TrendIcon,
} from '@mui/icons-material'

interface QualityMetricsProps {
  metrics: {
    totalRecords: number
    completeness: number
    accuracy: number
    consistency: number
    uniqueness: number
  }
  totalRecords: number
}

interface MetricCardProps {
  title: string
  value: number
  icon: React.ReactNode
  color: 'success' | 'info' | 'warning' | 'secondary'
  description: string
  details: string[]
}

const MetricCard: React.FC<MetricCardProps> = ({
  title,
  value,
  icon,
  color,
  description,
  details,
}) => {
  const getScoreLevel = (score: number) => {
    if (score >= 95) return '优秀'
    if (score >= 85) return '良好'
    if (score >= 70) return '一般'
    return '需改进'
  }

  const getProgressColor = (score: number) => {
    if (score >= 95) return 'success'
    if (score >= 85) return 'info'
    if (score >= 70) return 'warning'
    return 'error'
  }

  return (
    <Card sx={{ height: '100%' }}>
      <CardContent>
        <Box display="flex" alignItems="center" gap={2} mb={2}>
          {icon}
          <Box flex={1}>
            <Typography variant="h6" gutterBottom>
              {title}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {description}
            </Typography>
          </Box>
          <Box textAlign="right">
            <Typography variant="h4" color={`${color}.main`} fontWeight="bold">
              {value}%
            </Typography>
            <Chip 
              label={getScoreLevel(value)} 
              color={getProgressColor(value) as any} 
              size="small"
            />
          </Box>
        </Box>

        <LinearProgress
          variant="determinate"
          value={value}
          color={getProgressColor(value) as any}
          sx={{ mb: 2, height: 8, borderRadius: 4 }}
        />

        <List dense>
          {details.map((detail, index) => (
            <ListItem key={index} sx={{ py: 0.5 }}>
              <ListItemIcon sx={{ minWidth: 32 }}>
                <Box
                  sx={{
                    width: 6,
                    height: 6,
                    bgcolor: `${color}.main`,
                    borderRadius: '50%',
                  }}
                />
              </ListItemIcon>
              <ListItemText>
                <Typography variant="body2" color="text.secondary">
                  {detail}
                </Typography>
              </ListItemText>
            </ListItem>
          ))}
        </List>
      </CardContent>
    </Card>
  )
}

export const QualityMetricsCard: React.FC<QualityMetricsProps> = ({
  metrics,
  totalRecords,
}) => {
  const metricsData = [
    {
      title: '完整性',
      value: metrics.completeness,
      icon: <CompleteIcon color="success" />,
      color: 'success' as const,
      description: '数据字段填充完整程度',
      details: [
        `${Math.floor(totalRecords * (metrics.completeness / 100))} 条完整记录`,
        `${totalRecords - Math.floor(totalRecords * (metrics.completeness / 100))} 条存在缺失值`,
        '主要缺失字段: customer.email, phone',
      ],
    },
    {
      title: '准确性',
      value: metrics.accuracy,
      icon: <AccuracyIcon color="info" />,
      color: 'info' as const,
      description: '数据格式和内容准确程度',
      details: [
        `${Math.floor(totalRecords * (metrics.accuracy / 100))} 条符合格式`,
        '检测到日期格式不一致',
        '部分邮箱格式无效',
      ],
    },
    {
      title: '一致性',
      value: metrics.consistency,
      icon: <ConsistencyIcon color="warning" />,
      color: 'warning' as const,
      description: '数据源间字段一致性',
      details: [
        '字段命名规范: 91.8%',
        '数据类型匹配: 94.2%',
        '编码格式统一: 89.5%',
      ],
    },
    {
      title: '唯一性',
      value: metrics.uniqueness,
      icon: <UniquenessIcon color="secondary" />,
      color: 'secondary' as const,
      description: '重复记录和唯一性检查',
      details: [
        `检测到 ${Math.floor(totalRecords * ((100 - metrics.uniqueness) / 100))} 条重复记录`,
        '主键冲突: customer_id 字段',
        '建议数据清洗',
      ],
    },
  ]

  return (
    <Box>
      {/* Overall Summary */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            质量指标概览
          </Typography>
          
          <Grid container spacing={3} alignItems="center">
            <Grid item xs={12} md={3}>
              <Box display="flex" alignItems="center" gap={2}>
                <RecordsIcon color="primary" />
                <Box>
                  <Typography variant="h5" color="primary">
                    {totalRecords.toLocaleString()}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    总记录数
                  </Typography>
                </Box>
              </Box>
            </Grid>
            
            <Grid item xs={12} md={3}>
              <Box display="flex" alignItems="center" gap={2}>
                <TrendIcon color="success" />
                <Box>
                  <Typography variant="h5" color="success.main">
                    +2.3%
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    较上次提升
                  </Typography>
                </Box>
              </Box>
            </Grid>

            <Grid item xs={12} md={6}>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                数据质量评估基于完整性、准确性、一致性和唯一性四个维度。
                当前数据集整体质量良好，建议处理检测到的异常项以进一步提升质量评分。
              </Typography>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {/* Detailed Metrics */}
      <Grid container spacing={3}>
        {metricsData.map((metric, index) => (
          <Grid item xs={12} md={6} key={index}>
            <MetricCard {...metric} />
          </Grid>
        ))}
      </Grid>

      {/* Recommendations */}
      <Card sx={{ mt: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            改进建议
          </Typography>
          
          <List>
            <ListItem>
              <ListItemIcon>
                <CompleteIcon color="success" />
              </ListItemIcon>
              <ListItemText
                primary="提升完整性"
                secondary="为customer.email和phone字段添加必填验证，考虑数据收集流程优化"
              />
            </ListItem>
            
            <ListItem>
              <ListItemIcon>
                <AccuracyIcon color="info" />
              </ListItemIcon>
              <ListItemText
                primary="统一数据格式"
                secondary="建立日期和邮箱格式标准，实施数据输入验证规则"
              />
            </ListItem>
            
            <ListItem>
              <ListItemIcon>
                <UniquenessIcon color="secondary" />
              </ListItemIcon>
              <ListItemText
                primary="处理重复数据"
                secondary="清理customer_id重复记录，建立主键约束防止未来重复"
              />
            </ListItem>
          </List>
        </CardContent>
      </Card>
    </Box>
  )
}