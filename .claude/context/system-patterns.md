---
created: 2025-09-08T08:36:30Z
last_updated: 2025-09-08T08:36:30Z
version: 1.0
author: Claude Code PM System
---

# System Patterns

## Architectural Patterns

### Client-Server Architecture
- **Clean Separation**: Frontend and backend as separate services
- **API Gateway**: FastAPI serves as single entry point
- **Stateless Server**: No server-side session management
- **JSON Communication**: Standardized data exchange format

### Repository Pattern
```python
# db.py - Data access abstraction
def get_collection(collection_name):
    """Abstract MongoDB collection access"""
    
def sample_fields(collection, sample_size):
    """Standardized field discovery pattern"""
```

### Service Layer Pattern
```python
# app.py - Business logic separation  
@app.get("/api/collections")
def collections(): 
    return {"collections": list_collections()}

@app.post("/api/query")  
def query(request: QueryRequest):
    # Validation -> Business logic -> Response
```

## Data Flow Patterns

### Request-Response Cycle
1. **Frontend**: User interaction triggers API call
2. **Validation**: Pydantic models validate request data
3. **Processing**: Business logic manipulates data
4. **Database**: MongoDB query execution
5. **Response**: JSON serialization and return
6. **Frontend**: DOM update with new data

### Document Processing Pipeline
```python
# utils.py - Document transformation
def flatten_doc(doc):
    """Nested document -> flat key-value pairs"""
    
def safe_convert_value(value):
    """Type safety for JSON serialization"""
```

## Error Handling Patterns

### Global Error Handling
```python
# IFERROR pattern for division safety
if math.isnan(v) or math.isinf(v):
    return None  # Safe JSON conversion
```

### Graceful Degradation  
- **Missing Collections**: Empty list response
- **Invalid Queries**: FastAPI automatic 422 responses
- **File Upload Errors**: Detailed error messages
- **Encoding Issues**: Fallback with chardet

## State Management Patterns

### Frontend State
```javascript
// Global state variables
let currentData = [];
let currentPivot = {};
let filterState = {};

// Event-driven state updates
function updatePivotTable(data) {
    currentData = data;
    renderTable();
}
```

### Backend State
- **Stateless Design**: No server-side state storage
- **Database State**: Preferences persisted in MongoDB
- **Connection Pooling**: PyMongo handles connection state

## Configuration Patterns

### Environment-Based Configuration
```python
# Centralized environment variable access
MONGO_URI = os.getenv('MONGO_URI')
ALLOWED_COLLECTIONS = os.getenv('ALLOWED_COLLECTIONS', '').split(',')
```

### Template Pattern
```javascript
// config.template.js -> config.js
window.API_BASE = '${API_BASE}';  // Docker substitution
```

## Data Processing Patterns

### Schema Discovery Pattern
```python
def sample_fields(collection, sample_size=200):
    """Dynamic schema inference from data samples"""
    pipeline = [{"$sample": {"size": sample_size}}]
    # Analyze field types and patterns
```

### Document Flattening Pattern
```python
def flatten_doc(doc, prefix=''):
    """Recursive flattening of nested documents"""
    # user.profile.name -> user_profile_name
```

### Safe Type Conversion
```python  
def safe_convert_value(v):
    """JSON-safe value conversion with null fallbacks"""
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
```

## UI Patterns

### Progressive Enhancement
- **Basic HTML**: Works without JavaScript
- **CSS Enhancement**: Styled experience
- **JavaScript Enhancement**: Interactive features

### Event Delegation
```javascript
// Single event listener for dynamic content
document.addEventListener('click', function(e) {
    if (e.target.matches('.filter-button')) {
        handleFilterClick(e);
    }
});
```

### DOM Template Pattern
```javascript  
function createTableRow(data) {
    const row = document.createElement('tr');
    row.innerHTML = `<td>${data.field}</td><td>${data.value}</td>`;
    return row;
}
```

## Integration Patterns

### Docker Compose Service Discovery
```yaml
# Services communicate via container names
depends_on: [backend]  # Frontend waits for backend
```

### CORS Pattern
```python
# Development-friendly CORS
app.add_middleware(CORSMiddleware, 
    allow_origins=["*"],     # ⚠️ Production risk
    allow_headers=["*"], 
    allow_methods=["*"])
```

### File Upload Pattern
```python
@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    # Multipart form handling with type validation
```

## Performance Patterns

### Lazy Loading
- **Field Discovery**: On-demand schema sampling
- **Data Pagination**: Skip/limit pattern for large datasets
- **Dynamic Content**: DOM elements created as needed

### Caching Strategy
- **No Server Caching**: Stateless design
- **Browser Caching**: Standard HTTP caching headers
- **State Persistence**: LocalStorage for preferences