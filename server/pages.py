"""HTML pages: the splash screen and the app share one page, at /. And what the page needs to know."""
import os

from flask import Blueprint, jsonify, render_template, send_from_directory

from . import mailer
from .auth import pages_base
from .core import app_url
from .paths import BASE_PATH

pages_bp = Blueprint('pages', __name__)


@pages_bp.route('/')
def index():
    # Institution label under the wordmark, and the splash's "Learn more" link.
    # Override per deployment with environment variables.
    return render_template(
        'index.html',
        institution=os.environ.get('LECTERN_INSTITUTION', 'University of Toronto'),
        learn_more=os.environ.get('LECTERN_LEARN_MORE', ''),
    )


@pages_bp.get('/api/config')
def config():
    """Public settings: where the app and the published pages live, and whether email goes out."""
    return jsonify(app_url=app_url(), pages=pages_base(), email=mailer.configured(),
                   institution=os.environ.get('LECTERN_INSTITUTION', 'University of Toronto'))


@pages_bp.route('/manifest.json')
def manifest():
    return send_from_directory(BASE_PATH, 'manifest.json', mimetype='application/manifest+json')
