import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Stepper,
  Step,
  StepLabel,
  StepContent,
  Box,
  Button,
  Paper,
  Typography,
  Card,
  CardContent,
} from '@mui/material'
import { useBreakpoints } from '@/components/layout/ResponsiveGrid'
import { DataSourceSelection } from './steps/DataSourceSelection'
import { DataPreview } from './steps/DataPreview'
import { FieldMapping } from './steps/FieldMapping'
import { JoinConfiguration } from './steps/JoinConfiguration'
import { ExecutionConfirmation } from './steps/ExecutionConfirmation'

interface WizardData {
  dataSources: any[]
  previewData: Record<string, any[]>
  fieldMappings: any[]
  joinConfig: any
  executionSettings: any
}

const steps = [
  {
    label: '数据源选择',
    description: '选择要连接的数据源或上传文件',
  },
  {
    label: '数据预览',
    description: '查看字段结构和样本数据',
  },
  {
    label: '字段映射',
    description: '配置字段对应关系和类型转换',
  },
  {
    label: '连接配置',
    description: '设置连接类型和条件',
  },
  {
    label: '执行确认',
    description: '确认配置并执行连接操作',
  },
]

export const JoinWizard: React.FC = () => {
  const navigate = useNavigate()
  const [activeStep, setActiveStep] = useState(0)
  const [wizardData, setWizardData] = useState<WizardData>({
    dataSources: [],
    previewData: {},
    fieldMappings: [],
    joinConfig: {},
    executionSettings: {},
  })
  const { isMobile } = useBreakpoints()

  const handleNext = (): void => {
    if (activeStep === steps.length - 1) {
      // On final step, execute job and navigate to quality report
      handleFinish()
    } else {
      setActiveStep((prevActiveStep) => prevActiveStep + 1)
    }
  }

  const handleFinish = (): void => {
    // Generate a mock report ID
    const reportId = `report_${Date.now()}`
    console.log('Starting data join process with config:', wizardData)
    
    // Navigate to quality report page with running status
    navigate(`/quality-report/${reportId}`)
  }

  const handleBack = (): void => {
    setActiveStep((prevActiveStep) => prevActiveStep - 1)
  }

  const handleReset = (): void => {
    setActiveStep(0)
    setWizardData({
      dataSources: [],
      previewData: {},
      fieldMappings: [],
      joinConfig: {},
      executionSettings: {},
    })
  }

  const updateWizardData = (stepData: Partial<WizardData>): void => {
    setWizardData(prev => ({ ...prev, ...stepData }))
  }

  const isStepOptional = (step: number): boolean => {
    return false // No optional steps for now
  }

  const isStepCompleted = (step: number): boolean => {
    switch (step) {
      case 0:
        return wizardData.dataSources.length > 0
      case 1:
        return Object.keys(wizardData.previewData).length > 0
      case 2:
        return wizardData.fieldMappings.length > 0
      case 3:
        return Object.keys(wizardData.joinConfig).length > 0
      case 4:
        return Object.keys(wizardData.executionSettings).length > 0
      default:
        return false
    }
  }

  const renderStepContent = (step: number): React.ReactNode => {
    switch (step) {
      case 0:
        return (
          <DataSourceSelection
            dataSources={wizardData.dataSources}
            onUpdate={(dataSources) => updateWizardData({ dataSources })}
          />
        )
      case 1:
        return (
          <DataPreview
            dataSources={wizardData.dataSources}
            previewData={wizardData.previewData}
            onUpdate={(previewData) => updateWizardData({ previewData })}
          />
        )
      case 2:
        return (
          <FieldMapping
            previewData={wizardData.previewData}
            fieldMappings={wizardData.fieldMappings}
            onUpdate={(fieldMappings) => updateWizardData({ fieldMappings })}
          />
        )
      case 3:
        return (
          <JoinConfiguration
            fieldMappings={wizardData.fieldMappings}
            joinConfig={wizardData.joinConfig}
            onUpdate={(joinConfig) => updateWizardData({ joinConfig })}
          />
        )
      case 4:
        return (
          <ExecutionConfirmation
            wizardData={wizardData}
            onUpdate={(executionSettings) => updateWizardData({ executionSettings })}
          />
        )
      default:
        return <Typography>未知步骤</Typography>
    }
  }

  if (activeStep === steps.length) {
    return (
      <Paper square elevation={0} sx={{ p: 3 }}>
        <Typography>连接配置已完成！</Typography>
        <Button onClick={handleReset} sx={{ mt: 1, mr: 1 }}>
          重新开始
        </Button>
      </Paper>
    )
  }

  return (
    <Box>
      <Stepper 
        activeStep={activeStep} 
        orientation={isMobile ? 'vertical' : 'horizontal'}
        sx={{ mb: 3 }}
      >
        {steps.map((step, index) => (
          <Step key={step.label} completed={isStepCompleted(index)}>
            <StepLabel optional={isStepOptional(index) ? <Typography variant="caption">可选</Typography> : undefined}>
              {step.label}
            </StepLabel>
            {isMobile && (
              <StepContent>
                <Typography variant="body2" color="text.secondary">
                  {step.description}
                </Typography>
              </StepContent>
            )}
          </Step>
        ))}
      </Stepper>

      {!isMobile && (
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              {steps[activeStep].label}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {steps[activeStep].description}
            </Typography>
          </CardContent>
        </Card>
      )}

      <Paper sx={{ p: 3, mb: 3 }}>
        {renderStepContent(activeStep)}
      </Paper>

      {/* Navigation Buttons */}
      <Box sx={{ display: 'flex', flexDirection: 'row', pt: 2 }}>
        <Button
          color="inherit"
          disabled={activeStep === 0}
          onClick={handleBack}
          sx={{ mr: 1 }}
        >
          上一步
        </Button>
        <Box sx={{ flex: '1 1 auto' }} />
        {activeStep === steps.length - 1 ? (
          <Button onClick={handleNext} variant="contained" color="primary">
            开始执行
          </Button>
        ) : (
          <Button 
            onClick={handleNext} 
            variant="contained"
            disabled={!isStepCompleted(activeStep)}
          >
            下一步
          </Button>
        )}
      </Box>

      {/* Progress Indicator */}
      <Box sx={{ mt: 2, p: 2, bgcolor: 'background.default', borderRadius: 1 }}>
        <Typography variant="caption" color="text.secondary">
          进度: {activeStep + 1} / {steps.length} 
          {isStepCompleted(activeStep) && ' (✓ 已完成)'}
        </Typography>
      </Box>
    </Box>
  )
}