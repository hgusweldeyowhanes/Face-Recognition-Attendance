"""WSGI entrypoint for production servers (gunicorn / waitress / uwsgi)."""
from app import app

if __name__ == '__main__':
    import os
    from waitress import serve

    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', '5000'))
    serve(app, host=host, port=port, threads=4)
