import os
from datetime import timedelta

from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import URL
from werkzeug.middleware.proxy_fix import ProxyFix

db = SQLAlchemy()
jwt = JWTManager()
limiter = Limiter(key_func=get_remote_address, default_limits=["300 per hour"])


def database_url():
    if os.getenv("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    return URL.create(
        "mysql+pymysql",
        username=os.getenv("MYSQL_USER", "fraud"),
        password=os.getenv("MYSQL_PASSWORD", "fraud"),
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        database=os.getenv("MYSQL_DATABASE", "fraud_detection"),
    )


def create_app(test_config=None):
    app = Flask(__name__)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    app.config.update(
        SQLALCHEMY_DATABASE_URI=database_url(),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        JWT_SECRET_KEY=os.getenv("JWT_SECRET_KEY", ""),
        JWT_ACCESS_TOKEN_EXPIRES=timedelta(minutes=30),
        MAX_CONTENT_LENGTH=64 * 1024,
    )
    if test_config:
        app.config.update(test_config)
    if not app.config["JWT_SECRET_KEY"] and not app.testing:
        raise RuntimeError("JWT_SECRET_KEY must be configured before starting the API")

    origins = os.getenv("CORS_ORIGINS", "https://localhost")
    CORS(app, origins=[origin.strip() for origin in origins.split(",")])
    db.init_app(app)
    jwt.init_app(app)
    limiter.init_app(app)

    from app.routes import api

    app.register_blueprint(api, url_prefix="/api")
    from mgm_bank.routes import bank_api

    app.register_blueprint(bank_api, url_prefix="/api/bank")
    from app.commands import register_commands

    register_commands(app)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.errorhandler(413)
    def request_too_large(_error):
        return jsonify({"error": "Request body exceeds 64 KB"}), 413

    return app
