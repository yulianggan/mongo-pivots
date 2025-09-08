---
created: 2025-09-08T08:36:30Z
last_updated: 2025-09-08T08:36:30Z
version: 1.0
author: Claude Code PM System
---

# Project Overview

## Application Summary

**Mongo Pivot Suite** (蒙古数据透视套件) is a web-based data analysis tool that transforms MongoDB collections into interactive pivot tables. It provides business users with an intuitive drag-and-drop interface for exploring database content without requiring technical knowledge of MongoDB queries or aggregation pipelines.

## Current Feature Set

### Data Source Management
- **Collection Discovery**: Automatic listing of available MongoDB collections
- **Field Sampling**: Intelligent field detection with configurable sample sizes  
- **Data Preview**: Quick peek at collection contents with pagination
- **Schema Analysis**: Automatic type inference and field categorization

### Interactive Pivot Tables
- **Drag & Drop Interface**: Visual field assignment to pivot table dimensions
- **Multiple Aggregations**: Sum, count, average, minimum, maximum calculations
- **Dynamic Recalculation**: Real-time updates as configuration changes
- **Nested Grouping**: Multiple row and column grouping levels

### Advanced Filtering  
- **Multi-Field Filters**: Simultaneous filtering across multiple dimensions
- **Operator Support**: Equals, contains, greater than, less than, date ranges
- **Real-time Application**: Immediate pivot table updates on filter changes
- **Filter Persistence**: Save filter configurations with pivot preferences

### File Processing
- **Format Support**: CSV and Excel (.xlsx, .xls) file uploads
- **Encoding Detection**: Automatic character encoding recognition with chardet
- **Data Validation**: Type checking and error reporting during import
- **Integration**: Seamless combination with MongoDB collection data

### Configuration Management
- **Preference Storage**: MongoDB-based persistence of pivot configurations
- **Collection-Specific Settings**: Separate configurations per data source
- **Quick Restore**: One-click restoration of saved analysis setups
- **Configuration Export**: Share settings between users and environments

## Application State

### Production Readiness
- **Core Functionality**: ✅ Complete and tested
- **Error Handling**: ✅ Comprehensive error management
- **Performance**: ✅ Optimized for typical workloads  
- **Chinese Interface**: ✅ Fully localized user experience
- **Docker Deployment**: ✅ Production-ready containerization

### Known Limitations
- **No Authentication**: Open access to all features and data
- **Single Database**: Limited to one MongoDB instance per deployment
- **No Real-time Updates**: Manual refresh required for data changes
- **Limited Visualizations**: Text-based pivot tables only, no charts

### Recent Improvements
- **Enhanced Error Handling**: IFERROR global mechanisms for robust operation
- **CSV Processing**: Improved column recognition and encoding detection
- **Division Safety**: Mathematical error protection in aggregation calculations
- **File Upload**: Better support for various file formats and encodings

## Integration Points

### Database Integration
- **MongoDB Connection**: PyMongo driver with connection pooling
- **Query Optimization**: Efficient aggregation pipeline generation
- **Schema Flexibility**: Dynamic handling of varying document structures
- **Performance Scaling**: Pagination and sampling for large collections

### API Architecture
- **RESTful Design**: Standard HTTP methods and status codes
- **JSON Communication**: Consistent request/response formatting
- **CORS Support**: Cross-origin requests enabled for development
- **Error Standardization**: Uniform error response structure

### Deployment Integration
- **Docker Compose**: Multi-container orchestration
- **Environment Configuration**: Flexible deployment settings
- **Service Discovery**: Container-based service communication
- **Volume Persistence**: Data and configuration persistence

## User Experience

### Interface Design
- **Single Page Application**: Seamless user experience without page reloads
- **Responsive Layout**: Adaptable to different screen sizes
- **Intuitive Controls**: Drag-and-drop with clear visual feedback
- **Chinese Localization**: Native language interface throughout

### Workflow Patterns
1. **Data Discovery**: Browse collections → Sample fields → Preview data
2. **Pivot Creation**: Drag fields → Configure aggregations → Apply filters  
3. **Analysis Iteration**: Modify configuration → Review results → Refine filters
4. **Configuration Saving**: Store preferred setups → Quick restoration → Share configurations

### Performance Characteristics
- **Response Times**: Sub-second for typical pivot operations
- **Data Limits**: Handles collections with hundreds of thousands of documents
- **Memory Usage**: Efficient client-side rendering for large result sets
- **Network Efficiency**: Minimal data transfer through smart pagination

## Development Approach

### Technology Choices
- **Backend Simplicity**: FastAPI for rapid API development
- **Frontend Minimalism**: Vanilla JavaScript to avoid framework complexity
- **Database Native**: Direct MongoDB integration without ORM overhead
- **Container First**: Docker-based development and deployment

### Code Organization
- **Clear Separation**: Distinct backend and frontend codebases
- **Functional Design**: Utility-focused function organization
- **Configuration Driven**: Environment-based system configuration
- **Documentation Rich**: Comprehensive inline and external documentation

### Quality Assurance
- **Type Safety**: Pydantic models for data validation
- **Error Boundaries**: Comprehensive error handling at all levels
- **Data Safety**: JSON-safe value conversion and null handling
- **Input Validation**: Multi-layer validation from frontend to database