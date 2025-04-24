from flask import Flask
from flask_cors import CORS

def create_app():
    app = Flask(__name__, template_folder='../templates', static_folder='../static')
    app.config.from_object('app.config.Config')

    CORS(app)

    from .api.routes import api_bp
    app.register_blueprint(api_bp)

    return app
