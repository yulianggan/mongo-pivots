---
created: 2025-09-08T08:36:30Z
last_updated: 2025-09-08T08:36:30Z
version: 1.0
author: Claude Code PM System
---

# Project Structure

## Directory Organization

```
mongo_join_pivot/
├── .claude/                    # Claude Code configuration
│   ├── context/               # Project context documentation
│   ├── agents/               # Agent configurations
│   ├── rules/                # Development rules
│   └── scripts/              # Automation scripts
├── backend/                   # Python FastAPI backend
│   ├── app.py               # Main FastAPI application
│   ├── db.py                # MongoDB connection utilities
│   ├── models.py            # Pydantic data models
│   ├── prefs.py             # Preference storage
│   ├── utils.py             # Utility functions
│   ├── requirements.txt     # Python dependencies
│   └── Dockerfile           # Backend container config
├── frontend/                  # Vanilla JavaScript frontend
│   ├── index.html           # Single page application
│   ├── app.js               # Main application logic
│   ├── styles.css           # Application styling
│   ├── config.template.js   # Configuration template
│   ├── entrypoint.sh        # Container entrypoint
│   └── Dockerfile           # Frontend container config
├── install/                   # Installation scripts
├── ccpm_template/            # Claude Code PM template
├── docker-compose.yml        # Multi-container setup
├── .env.example             # Environment template
└── test_data.csv            # Sample data file
```

## File Naming Patterns

### Backend Files
- **Core Logic**: Single word descriptive names (app.py, db.py, utils.py)
- **Models**: Singular nouns (models.py, prefs.py)
- **Configuration**: Standard Python naming (requirements.txt, Dockerfile)

### Frontend Files  
- **Entry Point**: Standard web naming (index.html)
- **Scripts**: Descriptive purpose (app.js, config.js)
- **Styles**: Standard CSS naming (styles.css)
- **Templates**: Suffix pattern (config.template.js)

### Documentation
- **All Caps**: Key project files (CLAUDE.md, COMMANDS.md)
- **Descriptive**: Bug fix summaries with SCREAMING_SNAKE_CASE
- **Markdown**: All documentation in .md format

## Module Organization

### Backend Architecture
```python
app.py              # FastAPI routes and middleware
├── QueryRequest    # from models.py
├── list_collections# from db.py  
├── flatten_doc     # from utils.py
└── PrefsStore      # from prefs.py
```

### Frontend Architecture  
```javascript
app.js              # Monolithic client-side application
├── API calls       # Fetch-based HTTP requests
├── DOM manipulation# Vanilla JavaScript 
├── State management# Global variables
└── Event handling  # Direct event listeners
```

## Key Directories

### `.claude/`
Claude Code PM system configuration and project intelligence

### `backend/`
Python FastAPI server with MongoDB integration
- Clean separation of concerns
- Pydantic models for type safety
- Utility functions for data processing

### `frontend/`  
Single-page application with no framework dependencies
- Responsive CSS design
- Event-driven JavaScript architecture
- Dynamic content generation

### `install/`
Setup and installation utilities

## Import Patterns

### Backend Imports
- Standard library first
- Third-party packages second  
- Local modules last
- Relative imports for local modules

### Frontend Modules
- No module system - global scope
- Script tag order matters
- Configuration loaded first
- Main app.js loaded last

## Configuration Structure

### Environment Variables
- `.env` for local development
- `.env.example` as template
- Docker Compose variable substitution

### Container Configuration
- Multi-stage builds not used
- Separate Dockerfiles per service
- Compose orchestration for development