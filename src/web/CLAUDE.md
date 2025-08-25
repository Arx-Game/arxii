# Web - Django Web Interface

Django-based web interface for game management, character applications, and player tools. Supports both traditional Django views and modern API-driven frontend.

## Key Directories

### `api/`
- **`views/general_views.py`**: General API endpoints (stats, authentication)
- **`views/search_views.py`**: Search functionality across game data
- **`serializers.py`**: API response serialization
- **`exceptions.py`**: Custom API exception handling
- **`urls.py`**: API URL routing

### `admin/`
- **`urls.py`**: Admin interface URL configuration
- Custom admin interface extensions

### `static/`
- **`dist/`**: Built frontend assets from React application
- **`rest_framework/`**: Django REST framework static files
- **`webclient/`**: Traditional web client static files
- **`website/`**: General website static files

### `templates/`
- **`rest_framework/`**: API browsable interface templates
- **`webclient/`**: Traditional web client templates  
- **`website/`**: General website templates
- **`404.html`**, **`500.html`**: Error page templates

### `webclient/`
- **`message_types.py`**: WebSocket message type definitions
- **`urls.py`**: Web client URL routing
- Traditional web client functionality

### `website/`
- **`views/`**: General website view functions
- **`urls.py`**: Website URL routing

## Key Files

### `urls.py`
- Main URL configuration routing to all sub-applications
- Integrates API, admin, webclient, and website URLs

### `views.py`
- General web interface view functions
- Integration with Evennia web functionality

## Integration Points

- **REST API**: JSON endpoints for React frontend
- **WebSocket**: Real-time game communication
- **Authentication**: Django/Evennia account integration  
- **Static Files**: Serves built React application assets
