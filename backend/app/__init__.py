from flask import Flask
from flask_cors import CORS
from .security import init_security

def create_app():
    app = Flask(__name__)
    init_security(app)
    
    # Configure CORS
    CORS(app, resources={
        r"/api/*": {
            "origins": ["http://localhost:5173", "http://127.0.0.1:5173", "http://10.201.59.16:5173"],
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization", "Accept", "X-CSRF-Token"],
            "supports_credentials": True,
            "expose_headers": ["Content-Type", "Authorization"]
        }
    })
    print(f"CORS origins configured: {['http://localhost:5173', 'http://127.0.0.1:5173', 'http://10.201.59.16:5173']}")
    
    # Register blueprints here
    from .routes import main
    from .routes import database_routes
    from .routes import pipeline_routes
    from .routes import auth_routes
    from .routes import pms_fast_routes
    from .routes import fast_pipeline_routes
    from .routes import dedge_auth_routes
    from .routes import bar_hold_routes
    from .routes import stop_sale_routes
    app.register_blueprint(main.bp)
    app.register_blueprint(database_routes.bp)
    app.register_blueprint(pipeline_routes.bp)
    app.register_blueprint(auth_routes.bp)
    app.register_blueprint(pms_fast_routes.bp)
    app.register_blueprint(fast_pipeline_routes.bp)
    app.register_blueprint(dedge_auth_routes.bp)
    app.register_blueprint(bar_hold_routes.bp)
    app.register_blueprint(stop_sale_routes.bp)
    
    return app 