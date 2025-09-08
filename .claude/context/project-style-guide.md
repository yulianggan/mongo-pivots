---
created: 2025-09-08T08:36:30Z
last_updated: 2025-09-08T08:36:30Z
version: 1.0
author: Claude Code PM System
---

# Project Style Guide

## Python Backend Standards

### Code Organization
```python
# Import order: standard -> third-party -> local
import os
import math
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from db import get_collection
from utils import flatten_doc
```

### Function Naming
- **Descriptive verbs**: `list_collections()`, `sample_fields()`, `flatten_doc()`
- **Snake case**: All function names use underscores
- **Boolean functions**: Start with `is_` or `has_` when appropriate

### Class Naming  
```python
class QueryRequest(BaseModel):  # PascalCase for classes
    collection: str             # snake_case for attributes
    filters: Optional[Dict[str, Any]] = Field(default_factory=dict)
```

### Error Handling Pattern
```python
def safe_convert_value(v):
    """Convert value to JSON-safe format with null fallbacks"""
    if v is None:
        return None
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None  # Safe fallback for invalid floats
    return v
```

### Documentation Standards
- **Docstrings**: All functions have descriptive docstrings
- **Type hints**: Use typing module for complex types
- **Comments**: Explain business logic, not obvious code

## JavaScript Frontend Standards

### Variable Naming
```javascript
// camelCase for variables and functions
let currentData = [];
let pivotConfig = {};

// PascalCase for constructors (if used)
function PivotTable(container) { ... }

// UPPER_CASE for constants
const API_BASE_URL = window.API_BASE;
```

### Function Organization
```javascript
// Group related functions together
// DOM manipulation functions
function createElement(tag, className, content) { ... }
function updateTable(data) { ... }

// API communication functions  
async function fetchCollections() { ... }
async function postQuery(request) { ... }

// Event handler functions
function handleFilterClick(event) { ... }
function handleConfigChange(event) { ... }
```

### Async/Await Pattern
```javascript
// Consistent async/await usage
async function loadCollections() {
    try {
        const response = await fetch(`${API_BASE}/api/collections`);
        const data = await response.json();
        return data.collections;
    } catch (error) {
        console.error('Failed to load collections:', error);
        showError('无法加载集合列表');
        return [];
    }
}
```

## File Structure Patterns

### Backend File Organization
```
backend/
├── app.py          # Main FastAPI application
├── models.py       # Pydantic models
├── db.py           # Database utilities
├── utils.py        # Helper functions  
└── prefs.py        # Configuration management
```

### Frontend File Organization
```
frontend/
├── index.html      # Single page application
├── app.js          # Main application logic
├── styles.css      # Application styling
└── config.js       # Runtime configuration
```

### Configuration File Patterns
- **Environment templates**: `.env.example` for configuration examples
- **Docker files**: `Dockerfile` in each service directory
- **Compose configuration**: `docker-compose.yml` at project root

## CSS Standards

### Class Naming (BEM-inspired)
```css
/* Block-Element-Modifier pattern */
.filter-panel { }           /* Block */
.filter-panel__header { }   /* Element */  
.filter-panel--collapsed { } /* Modifier */

/* Utility classes */
.hidden { display: none; }
.loading { opacity: 0.5; }
```

### Responsive Design
```css
/* Mobile-first approach */
.container {
    width: 100%;
    padding: 1rem;
}

/* Desktop enhancements */
@media (min-width: 768px) {
    .container {
        max-width: 1200px;
        margin: 0 auto;
    }
}
```

## Comment Standards

### Python Comments
```python
def sample_fields(collection, sample_size=200):
    """
    Analyze collection fields through document sampling.
    
    Args:
        collection: MongoDB collection name
        sample_size: Number of documents to analyze
        
    Returns:
        List of field definitions with types and examples
    """
    # Use aggregation pipeline for efficient sampling
    pipeline = [{"$sample": {"size": sample_size}}]
    
    # Track field occurrences across sample
    field_stats = {}
```

### JavaScript Comments
```javascript
/**
 * Update pivot table display with new data
 * @param {Array} data - Array of aggregated records
 * @param {Object} config - Pivot configuration object
 */
function updatePivotTable(data, config) {
    // Clear existing table content
    const tableBody = document.querySelector('#pivot-table tbody');
    tableBody.innerHTML = '';
    
    // Generate table rows from pivot data
    data.forEach(row => {
        // Create row element with proper styling
        const tr = createElement('tr', 'data-row');
        // ... row generation logic
    });
}
```

## Error Message Standards

### User-Facing Messages (Chinese)
```javascript
const ERROR_MESSAGES = {
    CONNECTION_FAILED: '连接数据库失败，请检查配置',
    INVALID_COLLECTION: '指定的集合不存在',  
    UPLOAD_ERROR: '文件上传失败，请检查格式',
    PROCESSING_ERROR: '数据处理失败，请重试'
};
```

### Developer Messages (English)
```python
# Technical error messages for logs
logger.error(f"Failed to connect to MongoDB: {connection_string}")
logger.warning(f"Collection '{collection_name}' not found in allowed list")
```

## Configuration Patterns

### Environment Variable Naming
```bash
# Service configuration
BACKEND_PORT=7002
FRONTEND_PORT=5163

# Database configuration  
MONGO_URI=mongodb://host.docker.internal:27017
MONGO_DB=ozondatas

# Feature flags
ALLOWED_COLLECTIONS=collection1,collection2
PIVOT_PREFS_COLLECTION=pivot_prefs
```

### Docker Configuration
```dockerfile
# Multi-stage builds for production optimization
FROM python:3.11-slim as base
WORKDIR /app

# Dependency installation
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY . .
EXPOSE 8000
```

## Testing Patterns (Future)

### Backend Test Structure
```python
# test_api.py
class TestCollectionsAPI:
    def test_list_collections_success(self):
        """Test successful collection listing"""
        pass
        
    def test_list_collections_empty(self):
        """Test behavior with no collections"""
        pass
```

### Frontend Test Structure  
```javascript
// test_pivot.js
describe('Pivot Table', () => {
    it('should create table from data', () => {
        // Test implementation
    });
    
    it('should handle empty data gracefully', () => {
        // Test implementation  
    });
});
```