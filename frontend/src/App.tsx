import React from 'react'
import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom'
import { Box, AppBar, Toolbar, Typography, Button } from '@mui/material'
import { MainLayout } from '@/components/layout/MainLayout'
import { PivotPage } from '@/pages/PivotPage'
import { ConfigPage } from '@/pages/ConfigPage'

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
          </Routes>
        </MainLayout>
      </Box>
    </Router>
  )
}

export default App