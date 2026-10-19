"""HTML pages: the splash screen and the app share one page, at /."""
import os

from flask import Blueprint, render_template, send_from_directory

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


@pages_bp.route('/manifest.json')
def manifest():
    return send_from_directory(BASE_PATH, 'manifest.json', mimetype='application/manifest+json')
