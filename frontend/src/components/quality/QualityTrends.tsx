import React, { useState } from 'react'
import {
  Box,
  Typography,
  Grid,
  Card,
  CardContent,
  CardHeader,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Chip,
  Alert,
} from '@mui/material'
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  BarChart,
  Bar,
} from 'recharts'
import {
  TrendingUp as TrendUpIcon,
  TrendingDown as TrendDownIcon,
  TrendingFlat as TrendFlatIcon,
} from '@mui/icons-material'

interface QualityTrendsProps {
  reportId: string
}

export const QualityTrends: React.FC<QualityTrendsProps> = ({ reportId }) => {
  const [timeRange, setTimeRange] = useState('30d')
  const [selectedMetric, setSelectedMetric] = useState('overall')

  // Mock trend data
  const qualityTrendData = [
    { date: '2024-01-01', completeness: 92.1, accuracy: 87.3, consistency: 89.7, uniqueness: 95.2, overall: 91.1 },
    { date: '2024-01-02', completeness: 93.2, accuracy: 88.1, consistency: 90.2, uniqueness: 95.8, overall: 91.8 },
    { date: '2024-01-03', completeness: 92.8, accuracy: 88.9, consistency: 91.1, uniqueness: 96.1, overall: 92.2 },
    { date: '2024-01-04', completeness: 94.1, accuracy: 89.2, consistency: 91.5, uniqueness: 96.3, overall: 92.8 },
    { date: '2024-01-05', completeness: 93.7, accuracy: 89.8, consistency: 91.8, uniqueness: 96.5, overall: 93.0 },
    { date: '2024-01-06', completeness: 94.2, accuracy: 89.7, consistency: 91.8, uniqueness: 96.5, overall: 93.1 },
    { date: '2024-01-07', completeness: 94.2, accuracy: 89.7, consistency: 91.8, uniqueness: 96.5, overall: 93.1 },
  ]

  const anomalyTrendData = [
    { date: '2024-01-01', high: 3, medium: 8, low: 12 },
    { date: '2024-01-02', high: 2, medium: 7, low: 11 },
    { date: '2024-01-03', high: 2, medium: 6, low: 10 },
    { date: '2024-01-04', high: 1, medium: 5, low: 9 },
    { date: '2024-01-05', high: 1, medium: 4, low: 8 },
    { date: '2024-01-06', high: 1, medium: 3, low: 7 },
    { date: '2024-01-07', high: 1, medium: 3, low: 7 },
  ]

  const volumeTrendData = [
    { date: '2024-01-01', processed: 12847, errors: 234, success_rate: 98.2 },
    { date: '2024-01-02', processed: 13521, errors: 198, success_rate: 98.5 },
    { date: '2024-01-03', processed: 14203, errors: 156, success_rate: 98.9 },
    { date: '2024-01-04', processed: 14856, errors: 142, success_rate: 99.0 },
    { date: '2024-01-05', processed: 15234, errors: 123, success_rate: 99.2 },
    { date: '2024-01-06', processed: 15847, errors: 108, success_rate: 99.3 },
    { date: '2024-01-07', processed: 15847, errors: 108, success_rate: 99.3 },
  ]

  const handleTimeRangeChange = (event: React.ChangeEvent<{ value: unknown }>) => {
    setTimeRange(event.target.value as string)
  }

  const handleMetricChange = (event: React.ChangeEvent<{ value: unknown }>) => {
    setSelectedMetric(event.target.value as string)
  }

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('zh-CN', { 
      month: 'short', 
      day: 'numeric' 
    })
  }

  const getTrendIcon = (current: number, previous: number) => {
    if (current > previous) return <TrendUpIcon color="success" />
    if (current < previous) return <TrendDownIcon color="error" />
    return <TrendFlatIcon color="action" />
  }

  const getTrendPercentage = (current: number, previous: number) => {
    return ((current - previous) / previous * 100).toFixed(1)
  }

  // Calculate trend statistics
  const currentData = qualityTrendData[qualityTrendData.length - 1]
  const previousData = qualityTrendData[qualityTrendData.length - 2]

  const trendStats = [
    {
      label: '完整性',
      current: currentData.completeness,
      previous: previousData.completeness,
      color: 'success',
    },
    {
      label: '准确性',
      current: currentData.accuracy,
      previous: previousData.accuracy,
      color: 'info',
    },
    {
      label: '一致性',
      current: currentData.consistency,
      previous: previousData.consistency,
      color: 'warning',
    },
    {
      label: '唯一性',
      current: currentData.uniqueness,
      previous: previousData.uniqueness,
      color: 'secondary',
    },
  ]

  return (
    <Box>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h6">
          质量趋势分析
        </Typography>
        <Box display="flex" gap={2}>
          <FormControl size="small" sx={{ minWidth: 120 }}>
            <InputLabel>时间范围</InputLabel>
            <Select
              value={timeRange}
              onChange={handleTimeRangeChange}
              label="时间范围"
            >
              <MenuItem value="7d">最近7天</MenuItem>
              <MenuItem value="30d">最近30天</MenuItem>
              <MenuItem value="90d">最近90天</MenuItem>
            </Select>
          </FormControl>
        </Box>
      </Box>
      
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        跟踪数据质量指标的历史变化趋势，识别质量改进和退化模式。
      </Typography>

      {/* Trend Summary Cards */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        {trendStats.map((stat, index) => (
          <Grid item xs={12} md={3} key={index}>
            <Card>
              <CardContent>
                <Box display="flex" alignItems="center" justifyContent="space-between">
                  <Box>
                    <Typography variant="body2" color="text.secondary">
                      {stat.label}
                    </Typography>
                    <Typography variant="h5" color={`${stat.color}.main`}>
                      {stat.current.toFixed(1)}%
                    </Typography>
                  </Box>
                  <Box display="flex" alignItems="center" gap={1}>
                    {getTrendIcon(stat.current, stat.previous)}
                    <Typography 
                      variant="body2" 
                      color={stat.current >= stat.previous ? 'success.main' : 'error.main'}
                    >
                      {stat.current >= stat.previous ? '+' : ''}
                      {getTrendPercentage(stat.current, stat.previous)}%
                    </Typography>
                  </Box>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      {/* Quality Metrics Trend Chart */}
      <Grid container spacing={3}>
        <Grid item xs={12} lg={8}>
          <Card>
            <CardHeader 
              title="质量指标趋势"
              action={
                <FormControl size="small" sx={{ minWidth: 120 }}>
                  <InputLabel>显示指标</InputLabel>
                  <Select
                    value={selectedMetric}
                    onChange={handleMetricChange}
                    label="显示指标"
                  >
                    <MenuItem value="overall">综合评分</MenuItem>
                    <MenuItem value="all">所有指标</MenuItem>
                    <MenuItem value="completeness">完整性</MenuItem>
                    <MenuItem value="accuracy">准确性</MenuItem>
                    <MenuItem value="consistency">一致性</MenuItem>
                    <MenuItem value="uniqueness">唯一性</MenuItem>
                  </Select>
                </FormControl>
              }
            />
            <CardContent>
              <Box height={400}>
                <ResponsiveContainer width="100%" height="100%">
                  {selectedMetric === 'all' ? (
                    <LineChart data={qualityTrendData}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis 
                        dataKey="date" 
                        tickFormatter={formatDate}
                      />
                      <YAxis domain={[80, 100]} />
                      <Tooltip 
                        labelFormatter={(label) => formatDate(label)}
                        formatter={(value, name) => [
                          `${Number(value).toFixed(1)}%`, 
                          name === 'completeness' ? '完整性' :
                          name === 'accuracy' ? '准确性' :
                          name === 'consistency' ? '一致性' :
                          name === 'uniqueness' ? '唯一性' : name
                        ]}
                      />
                      <Legend 
                        formatter={(value) => 
                          value === 'completeness' ? '完整性' :
                          value === 'accuracy' ? '准确性' :
                          value === 'consistency' ? '一致性' :
                          value === 'uniqueness' ? '唯一性' : value
                        }
                      />
                      <Line 
                        type="monotone" 
                        dataKey="completeness" 
                        stroke="#4caf50" 
                        strokeWidth={2}
                        dot={{ r: 4 }}
                      />
                      <Line 
                        type="monotone" 
                        dataKey="accuracy" 
                        stroke="#2196f3" 
                        strokeWidth={2}
                        dot={{ r: 4 }}
                      />
                      <Line 
                        type="monotone" 
                        dataKey="consistency" 
                        stroke="#ff9800" 
                        strokeWidth={2}
                        dot={{ r: 4 }}
                      />
                      <Line 
                        type="monotone" 
                        dataKey="uniqueness" 
                        stroke="#9c27b0" 
                        strokeWidth={2}
                        dot={{ r: 4 }}
                      />
                    </LineChart>
                  ) : (
                    <AreaChart data={qualityTrendData}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis 
                        dataKey="date" 
                        tickFormatter={formatDate}
                      />
                      <YAxis domain={[80, 100]} />
                      <Tooltip 
                        labelFormatter={(label) => formatDate(label)}
                        formatter={(value) => [`${Number(value).toFixed(1)}%`, '质量评分']}
                      />
                      <Area
                        type="monotone"
                        dataKey={selectedMetric}
                        stroke="#2196f3"
                        fill="#2196f3"
                        fillOpacity={0.3}
                        strokeWidth={2}
                      />
                    </AreaChart>
                  )}
                </ResponsiveContainer>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} lg={4}>
          <Card sx={{ mb: 3 }}>
            <CardHeader title="异常数量趋势" />
            <CardContent>
              <Box height={200}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={anomalyTrendData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis 
                      dataKey="date" 
                      tickFormatter={formatDate}
                    />
                    <YAxis />
                    <Tooltip 
                      labelFormatter={(label) => formatDate(label)}
                      formatter={(value, name) => [
                        value, 
                        name === 'high' ? '高优先级' :
                        name === 'medium' ? '中优先级' :
                        name === 'low' ? '低优先级' : name
                      ]}
                    />
                    <Bar dataKey="high" fill="#f44336" name="high" />
                    <Bar dataKey="medium" fill="#ff9800" name="medium" />
                    <Bar dataKey="low" fill="#2196f3" name="low" />
                  </BarChart>
                </ResponsiveContainer>
              </Box>
            </CardContent>
          </Card>

          <Card>
            <CardHeader title="处理量趋势" />
            <CardContent>
              <Box height={200}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={volumeTrendData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis 
                      dataKey="date" 
                      tickFormatter={formatDate}
                    />
                    <YAxis />
                    <Tooltip 
                      labelFormatter={(label) => formatDate(label)}
                      formatter={(value, name) => [
                        name === 'success_rate' ? `${Number(value).toFixed(1)}%` : Number(value).toLocaleString(),
                        name === 'processed' ? '处理记录数' :
                        name === 'errors' ? '错误数' :
                        name === 'success_rate' ? '成功率' : name
                      ]}
                    />
                    <Line 
                      type="monotone" 
                      dataKey="processed" 
                      stroke="#4caf50" 
                      strokeWidth={2}
                      yAxisId="left"
                    />
                    <Line 
                      type="monotone" 
                      dataKey="errors" 
                      stroke="#f44336" 
                      strokeWidth={2}
                      yAxisId="left"
                    />
                  </LineChart>
                </ResponsiveContainer>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Insights */}
      <Card sx={{ mt: 3 }}>
        <CardHeader title="趋势洞察" />
        <CardContent>
          <Grid container spacing={2}>
            <Grid item xs={12} md={6}>
              <Alert severity="success" sx={{ mb: 2 }}>
                <Typography variant="subtitle2" gutterBottom>
                  质量改善趋势
                </Typography>
                <Typography variant="body2">
                  数据完整性在过去7天提升了{getTrendPercentage(currentData.completeness, qualityTrendData[0].completeness)}%，
                  异常检测数量减少了{Math.abs(Number(getTrendPercentage(7, 23)))}%。
                </Typography>
              </Alert>
            </Grid>
            
            <Grid item xs={12} md={6}>
              <Alert severity="info">
                <Typography variant="subtitle2" gutterBottom>
                  处理量增长
                </Typography>
                <Typography variant="body2">
                  每日处理记录数较初期增长了{getTrendPercentage(15847, 12847)}%，
                  系统处理能力稳步提升。
                </Typography>
              </Alert>
            </Grid>
          </Grid>
        </CardContent>
      </Card>
    </Box>
  )
}