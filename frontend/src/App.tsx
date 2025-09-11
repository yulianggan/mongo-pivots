import React from 'react'
import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom'
import { Box, AppBar, Toolbar, Typography, Button } from '@mui/material'
import { MainLayout } from '@/components/layout/MainLayout'
import { PivotPage } from '@/pages/PivotPage'
import { ConfigPage } from '@/pages/ConfigPage'
import { DataSourcePage } from '@/pages/DataSourcePage'
import { JoinWizardPage } from '@/pages/JoinWizardPage'
import { QualityReportPage } from '@/pages/QualityReportPage'
import { PivotFromJoinPage } from '@/pages/PivotFromJoinPage'

const App: React.FC = () => {
  return (
    <Router>
      <Box sx={{ flexGrow: 1 }}>
        <AppBar position="static" sx={{ mb: 2 }}>
          <Toolbar>
            <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
              Mongo Pivot Suite 2.0
            </Typography>
            <Button color="inherit" component={Link} to="/pivot">
              透视表
            </Button>
            <Button color="inherit" component={Link} to="/datasource">
              数据源
            </Button>
            <Button color="inherit" component={Link} to="/join-wizard">
              连接向导
            </Button>
            <Button color="inherit" component={Link} to="/config">
              配置
            </Button>
          </Toolbar>
        </AppBar>
        
        <MainLayout>
          <Routes>
            <Route path="/" element={<PivotPage />} />
            <Route path="/config" element={<ConfigPage />} />
            <Route path="/pivot" element={<PivotPage />} />
            <Route path="/datasource" element={<DataSourcePage />} />
            <Route path="/join-wizard" element={<JoinWizardPage />} />
            <Route path="/quality-report/:reportId?" element={<QualityReportPage />} />
            <Route path="/pivot-from-join/:resultId" element={<PivotFromJoinPage />} />
          </Routes>
        </MainLayout>
      </Box>
    </Router>
  )
}

export default App