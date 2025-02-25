from celery import Celery
from app import create_app

def create_celery_app(app=None):
    """Attach Celery to the given Flask app."""
    app = app or create_app()
    celery = Celery(
        app.import_name,
        broker='redis://localhost:6379/0',
        backend='redis://localhost:6379/0',
        include=['tasks']
    )
    celery.conf.update(app.config)

    class ContextTask(celery.Task):
        """Make Celery tasks aware of Flask app context."""
        abstract = True
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return super().__call__(*args, **kwargs)

    celery.Task = ContextTask
    return celery

# Create the global Flask + Celery so tasks can import them
flask_app = create_app()
celery = create_celery_app(flask_app)
