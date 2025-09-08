---
created: 2025-09-08T08:36:30Z
last_updated: 2025-09-08T08:36:30Z
version: 1.0
author: Claude Code PM System
---

# Technology Context

## Language & Runtime

### Backend Stack
- **Python**: Primary backend language
- **FastAPI**: Modern web framework for APIs
- **Uvicorn**: ASGI server with auto-reload capability

### Frontend Stack  
- **HTML5**: Semantic markup with Chinese language support
- **CSS3**: Modern styling with flexbox and grid
- **JavaScript ES6+**: Vanilla JavaScript, no frameworks

## Core Dependencies

### Backend Dependencies (requirements.txt)
```python
fastapi>=0.111.0        # Web framework
uvicorn[standard]>=0.30.0  # ASGI server
pymongo>=4.8.0          # MongoDB driver
pydantic>=2.6.0         # Data validation
pandas>=2.2.2           # Data processing
openpyxl>=3.1.2         # Excel file support
xlrd>=2.0.1             # Excel file reading
python-multipart>=0.0.9 # File upload support
chardet>=5.0.0          # Character encoding detection
```

### Frontend Dependencies
- **No JavaScript frameworks** - Vanilla implementation
- **No CSS frameworks** - Custom styling
- **No build tools** - Direct browser execution

## Database Technology

### MongoDB
- **Version**: Compatible with 4.8+ driver
- **Connection**: PyMongo with connection pooling
- **Schema**: Schemaless with dynamic field discovery
- **Collections**: Configurable via environment variables

## Development Tools

### Containerization
- **Docker**: Multi-container development environment  
- **Docker Compose**: Service orchestration
- **Alpine Linux**: Lightweight base images

### Version Control
- **Git**: Standard source control
- **GitHub**: Remote repository hosting
- **Branch Strategy**: Single master branch currently

## Architecture Decisions

### Backend Design
- **RESTful API**: Standard HTTP verbs and status codes
- **CORS Enabled**: Wildcard origins for development
- **JSON Communication**: Standard request/response format
- **Error Handling**: FastAPI automatic error responses

### Frontend Design
- **SPA Architecture**: Single page application
- **DOM Manipulation**: Direct JavaScript, no virtual DOM
- **State Management**: Global variables and local storage
- **Event-Driven**: DOM event listeners for interactions

### Data Processing
- **Server-Side**: Heavy lifting done in Python
- **Client-Side**: UI updates and user interactions
- **File Processing**: Pandas for CSV/Excel handling
- **Encoding Detection**: Automatic with chardet

## Configuration Management

### Environment Variables
```bash
BACKEND_PORT=7002           # API server port
FRONTEND_PORT=5163          # Web server port  
MONGO_URI=mongodb://...     # Database connection
MONGO_DB=ozondatas         # Target database
ALLOWED_COLLECTIONS=...    # Comma-separated list
PIVOT_PREFS_COLLECTION=... # Preferences storage
API_BASE=http://localhost... # Frontend API endpoint
```

### Runtime Configuration
- **Hot Reload**: Uvicorn development mode
- **Auto Discovery**: Dynamic MongoDB schema detection
- **Preference Persistence**: MongoDB-based settings storage

## Performance Considerations

### Backend Optimizations
- **Async Framework**: FastAPI with async/await support
- **Connection Pooling**: MongoDB driver handles connections
- **Pagination**: Skip/limit for large datasets
- **Field Sampling**: Intelligent schema detection

### Frontend Optimizations  
- **Minimal Dependencies**: No framework overhead
- **Direct DOM**: No virtual DOM reconciliation
- **Lazy Loading**: Dynamic content generation
- **Local Caching**: Browser-based state persistence

## Security Context

### Current Implementation
- **CORS**: Wide open for development (⚠️ production concern)
- **No Authentication**: Open access to all endpoints
- **Input Validation**: Pydantic model validation
- **File Upload**: Basic multipart form support

### Security Recommendations
- Implement authentication middleware
- Restrict CORS origins for production
- Add input sanitization for MongoDB queries
- Implement rate limiting for API endpoints