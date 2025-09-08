# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> Think carefully and implement the most concise solution that changes as little code as possible.

## Project Architecture

This is a MongoDB data visualization and pivoting application with a FastAPI backend and vanilla JavaScript frontend.

### Backend (Python/FastAPI)
- **Framework**: FastAPI with uvicorn server
- **Database**: MongoDB with pymongo driver
- **Main files**:
  - `backend/app.py`: Main FastAPI application with API endpoints
  - `backend/models.py`: Pydantic models for request/response schemas
  - `backend/db.py`: MongoDB connection and query utilities
  - `backend/utils.py`: Utility functions (document flattening)
  - `backend/prefs.py`: Preference storage for pivot configurations

### Frontend (Vanilla JavaScript)
- **Stack**: Pure HTML/CSS/JavaScript (no framework)
- **Main files**:
  - `frontend/index.html`: Single-page application UI
  - `frontend/app.js`: Main JavaScript application logic
  - `frontend/styles.css`: Application styling
  - `frontend/config.js`: Configuration (generated from template)

### Architecture Patterns
- **Data Flow**: Frontend → FastAPI API → MongoDB
- **Configuration**: Environment variables through Docker
- **Deployment**: Docker Compose with separate containers
- **Data Processing**: Server-side aggregation with client-side pivot table rendering

## Development Commands

### Docker Development
```bash
# Start the full stack
docker-compose up --build

# Start in detached mode
docker-compose up -d --build

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### Backend Development
```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Run development server
uvicorn app:app --reload --port 8000

# Run with specific host
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

### Environment Configuration
- Copy `.env.example` to `.env` and configure:
  - `MONGO_URI`: MongoDB connection string
  - `MONGO_DB`: Target database name
  - `ALLOWED_COLLECTIONS`: Comma-separated collection names
  - `BACKEND_PORT` / `FRONTEND_PORT`: Service ports

## Key APIs and Endpoints

### Data APIs
- `GET /api/collections` - List available MongoDB collections
- `GET /api/fields?collection=X&sample=N` - Sample fields from collection
- `GET /api/peek?collection=X&limit=N` - Preview collection data
- `POST /api/query` - Execute MongoDB query with filters
- `POST /api/upload` - Upload CSV/Excel files for processing

### Configuration APIs  
- `GET /api/prefs/{collection}` - Get saved pivot preferences
- `POST /api/prefs/{collection}` - Save pivot preferences

## Database Schema

### Core Models
- **QueryRequest** (Pydantic): MongoDB query parameters with filters, limits, projections
- Collections are dynamic - structure discovered at runtime through field sampling

### Preferences Storage
- Pivot table configurations stored in `PIVOT_PREFS_COLLECTION`
- Keyed by collection name for persistence across sessions

## Testing Strategy

Currently no automated tests exist. When adding tests:
- Use pytest for backend testing
- Test API endpoints with FastAPI TestClient
- Mock MongoDB operations for unit tests
- Test file upload functionality with sample data

## Development Notes

### Data Handling
- Documents are flattened using dot notation (e.g., `user.name` becomes `user_name`)
- JSON-unsafe values (NaN, Infinity) are converted to null
- Large datasets are paginated with skip/limit parameters

### File Processing
- Supports CSV and Excel file uploads
- Automatic encoding detection with chardet
- Pandas used for data processing and format conversion

### Frontend State Management
- No framework - uses vanilla DOM manipulation
- State stored in global JavaScript objects
- Real-time filtering and pivot table updates

### Error Handling
- FastAPI automatic error responses
- Frontend displays user-friendly error messages
- MongoDB connection errors gracefully handled