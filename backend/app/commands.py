import getpass

import click

from app import db
from app.models import User


def register_commands(app):
    @app.cli.command("init-db")
    def init_db():
        """Create the initial MySQL tables for a fresh local installation."""
        from app import models  # noqa: F401
        from mgm_bank import models as bank_models  # noqa: F401
        from mgm_bank.service import ensure_accounts_for_existing_users

        db.create_all()
        ensure_accounts_for_existing_users()
        click.echo("Database tables are ready.")

    @app.cli.command("create-admin")
    @click.option("--email", prompt=True)
    def create_admin(email):
        """Create an administrator using an interactive password prompt."""
        email = email.strip().lower()
        if User.query.filter_by(email=email).first():
            raise click.ClickException("An account with that email already exists")
        password = getpass.getpass("Administrator password (12+ characters): ")
        if len(password) < 12:
            raise click.ClickException("Password must contain at least 12 characters")
        user = User(email=email, role="admin")
        user.set_password(password)
        db.session.add(user)
        from mgm_bank.service import ensure_customer_account

        db.session.flush()
        ensure_customer_account(user)
        db.session.commit()
        click.echo(f"Administrator account created: {email}")
