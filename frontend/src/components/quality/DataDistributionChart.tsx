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
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  LinearProgress,
} from '@mui/material'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
  LineChart,
  Line,
  Area,
  AreaChart,
} from 'recharts'

interface DataDistributionChartProps {
  reportId: string
  data: any
}

interface FieldDistribution {
  fieldName: string
  dataType: string
  nullCount: number
  uniqueCount: number
  totalCount: number
  nullPercentage: number
  topValues: Array<{
    value: string
    count: number
    percentage: number
  }>
}

const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884D8', '#82CA9D']

export const DataDistributionChart: React.FC<DataDistributionChartProps> = ({
  reportId,
  data,
}) => {
  const [selectedField, setSelectedField] = useState('customer_id')

  // Mock field distribution data
  const fieldDistributions: FieldDistribution[] = [
    {
      fieldName: 'customer_id',
      dataType: 'string',
      nullCount: 0,
      uniqueCount: 15847,
      totalCount: 15847,
      nullPercentage: 0,
      topValues: [
        { value: 'C001', count: 1, percentage: 0.006 },
        { value: 'C002', count: 1, percentage: 0.006 },
        { value: 'C003', count: 1, percentage: 0.006 },
      ],
    },
    {
      fieldName: 'customer.email',
      dataType: 'string',
      nullCount: 234,
      uniqueCount: 15613,
      totalCount: 15847,
      nullPercentage: 1.48,
      topValues: [
        { value: 'gmail.com', count: 8542, percentage: 53.9 },
        { value: '163.com', count: 3421, percentage: 21.6 },
        { value: 'qq.com', count: 2156, percentage: 13.6 },
        { value: 'sina.com', count: 1494, percentage: 9.4 },
      ],
    },
    {
      fieldName: 'order_amount',
      dataType: 'number',
      nullCount: 12,
      uniqueCount: 1547,
      totalCount: 15847,
      nullPercentage: 0.08,
      topValues: [
        { value: '0-100', count: 3542, percentage: 22.4 },
        { value: '100-500', count: 6821, percentage: 43.1 },
        { value: '500-1000', count: 3456, percentage: 21.8 },
        { value: '1000+', count: 2016, percentage: 12.7 },
      ],
    },
  ]

  const currentField = fieldDistributions.find(f => f.fieldName === selectedField) || fieldDistributions[0]

  // Data type distribution
  const dataTypeDistribution = [
    { name: 'String', value: 12, color: '#0088FE' },
    { name: 'Number', value: 8, color: '#00C49F' },
    { name: 'Date', value: 4, color: '#FFBB28' },
    { name: 'Boolean', value: 2, color: '#FF8042' },
  ]

  // Null value distribution across fields
  const nullDistribution = fieldDistributions.map(field => ({
    name: field.fieldName.split('.').pop() || field.fieldName,
    nullPercentage: field.nullPercentage,
    validPercentage: 100 - field.nullPercentage,
  }))

  // Value distribution for current field
  const valueDistributionData = currentField.topValues.map(item => ({
    name: item.value,
    count: item.count,
    percentage: item.percentage,
  }))

  const handleFieldChange = (event: React.ChangeEvent<{ value: unknown }>) => {
    setSelectedField(event.target.value as string)
  }

  return (
    <Box>
      <Typography variant="h6" gutterBottom>
        数据分布分析
      </Typography>
      
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        分析数据字段的分布情况、数据类型组成和缺失值分布，帮助了解数据质量状况。
      </Typography>

      <Grid container spacing={3}>
        {/* Data Type Distribution */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardHeader title="数据类型分布" />
            <CardContent>
              <Box height={300}>
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={dataTypeDistribution}
                      cx="50%"
                      cy="50%"
                      labelLine={false}
                      label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
                      outerRadius={80}
                      fill="#8884d8"
                      dataKey="value"
                    >
                      {dataTypeDistribution.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Null Value Distribution */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardHeader title="缺失值分布" />
            <CardContent>
              <Box height={300}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={nullDistribution}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis 
                      dataKey="name" 
                      angle={-45}
                      textAnchor="end"
                      height={80}
                    />
                    <YAxis />
                    <Tooltip 
                      formatter={(value, name) => [
                        `${value}%`, 
                        name === 'nullPercentage' ? '缺失率' : '完整率'
                      ]}
                    />
                    <Bar dataKey="nullPercentage" fill="#FF8042" name="缺失率" />
                    <Bar dataKey="validPercentage" fill="#00C49F" name="完整率" />
                  </BarChart>
                </ResponsiveContainer>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Field Distribution Analysis */}
        <Grid item xs={12}>
          <Card>
            <CardHeader 
              title="字段分布详情"
              action={
                <FormControl sx={{ minWidth: 200 }}>
                  <InputLabel>选择字段</InputLabel>
                  <Select
                    value={selectedField}
                    onChange={handleFieldChange}
                    label="选择字段"
                  >
                    {fieldDistributions.map(field => (
                      <MenuItem key={field.fieldName} value={field.fieldName}>
                        {field.fieldName}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              }
            />
            <CardContent>
              <Grid container spacing={3}>
                {/* Field Statistics */}
                <Grid item xs={12} md={4}>
                  <Box>
                    <Typography variant="subtitle2" gutterBottom>
                      字段统计
                    </Typography>
                    
                    <Box display="flex" flexDirection="column" gap={2}>
                      <Box>
                        <Typography variant="body2" color="text.secondary">
                          数据类型
                        </Typography>
                        <Chip 
                          label={currentField.dataType} 
                          color="primary" 
                          size="small" 
                        />
                      </Box>
                      
                      <Box>
                        <Typography variant="body2" color="text.secondary">
                          总记录数
                        </Typography>
                        <Typography variant="h6">
                          {currentField.totalCount.toLocaleString()}
                        </Typography>
                      </Box>
                      
                      <Box>
                        <Typography variant="body2" color="text.secondary">
                          唯一值数量
                        </Typography>
                        <Typography variant="h6" color="success.main">
                          {currentField.uniqueCount.toLocaleString()}
                        </Typography>
                      </Box>
                      
                      <Box>
                        <Typography variant="body2" color="text.secondary">
                          缺失值
                        </Typography>
                        <Typography 
                          variant="h6" 
                          color={currentField.nullCount > 0 ? "warning.main" : "success.main"}
                        >
                          {currentField.nullCount.toLocaleString()} ({currentField.nullPercentage}%)
                        </Typography>
                        <LinearProgress 
                          variant="determinate" 
                          value={100 - currentField.nullPercentage}
                          color={currentField.nullPercentage > 5 ? "warning" : "success"}
                          sx={{ mt: 1 }}
                        />
                      </Box>
                    </Box>
                  </Box>
                </Grid>

                {/* Value Distribution Chart */}
                <Grid item xs={12} md={8}>
                  <Typography variant="subtitle2" gutterBottom>
                    值分布图表
                  </Typography>
                  
                  <Box height={300}>
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={valueDistributionData}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="name" />
                        <YAxis />
                        <Tooltip 
                          formatter={(value, name) => [
                            name === 'count' ? value : `${value}%`,
                            name === 'count' ? '数量' : '占比'
                          ]}
                        />
                        <Bar dataKey="count" fill="#0088FE" name="数量" />
                      </BarChart>
                    </ResponsiveContainer>
                  </Box>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>

        {/* Top Values Table */}
        <Grid item xs={12}>
          <Card>
            <CardHeader title={`${currentField.fieldName} - 高频值分析`} />
            <CardContent>
              <TableContainer component={Paper} variant="outlined">
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableCell>值</TableCell>
                      <TableCell align="right">数量</TableCell>
                      <TableCell align="right">占比</TableCell>
                      <TableCell>分布</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {currentField.topValues.map((item, index) => (
                      <TableRow key={index}>
                        <TableCell>
                          <Typography variant="body2">
                            {item.value}
                          </Typography>
                        </TableCell>
                        <TableCell align="right">
                          <Typography variant="body2">
                            {item.count.toLocaleString()}
                          </Typography>
                        </TableCell>
                        <TableCell align="right">
                          <Typography variant="body2">
                            {item.percentage.toFixed(1)}%
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Box display="flex" alignItems="center" gap={1}>
                            <LinearProgress
                              variant="determinate"
                              value={Math.min(item.percentage, 100)}
                              sx={{ flex: 1, height: 8, borderRadius: 4 }}
                            />
                          </Box>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  )
}