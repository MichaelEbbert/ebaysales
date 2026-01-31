from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from models import db, Card, Listing, Order
from datetime import datetime, timedelta
from dateutil import tz
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import anthropic
import base64
import os
import cv2
import numpy as np
from PIL import Image

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///ebaysales.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'tif', 'tiff'}

db.init_app(app)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def auto_crop_card(filepath):
    """
    Crop a trading card scan to fixed dimensions.
    Assumes card in penny sleeve is flush to top-left corner at 600 DPI.

    Card: 2.5" x 3.5" = 1500 x 2100 pixels at 600 DPI
    Penny sleeve adds: 3mm left, 3mm right, 5mm top, 3mm bottom
    At 600 DPI: 1mm = 23.62 pixels
    """
    # Read image with OpenCV
    img = cv2.imread(filepath)
    if img is None:
        return filepath

    # Dimensions at 600 DPI
    mm_to_px = 600 / 25.4  # ~23.62 pixels per mm

    card_width = int(2.5 * 600)   # 1500px
    card_height = int(3.5 * 600)  # 2100px

    sleeve_left = int(3 * mm_to_px)    # ~71px
    sleeve_right = int(3 * mm_to_px)   # ~71px
    sleeve_top = int(5 * mm_to_px)     # ~118px
    sleeve_bottom = int(3 * mm_to_px)  # ~71px

    cushion = 5  # 5px extra border

    # Total crop dimensions (sleeved card + cushion on right/bottom only since flush to corner)
    crop_width = sleeve_left + card_width + sleeve_right + cushion
    crop_height = sleeve_top + card_height + sleeve_bottom + cushion

    # Make sure we don't exceed image bounds
    crop_width = min(crop_width, img.shape[1])
    crop_height = min(crop_height, img.shape[0])

    # Crop from top-left corner
    cropped = img[0:crop_height, 0:crop_width]

    # Save the cropped image
    cv2.imwrite(filepath, cropped)

    return filepath

# Timezone for Saturday 11pm target
EASTERN = tz.gettz('America/New_York')


def get_next_saturday_11pm():
    """Calculate the next Saturday at 11:00 PM Eastern."""
    now = datetime.now(EASTERN)
    days_until_saturday = (5 - now.weekday()) % 7
    if days_until_saturday == 0 and now.hour >= 23:
        days_until_saturday = 7
    next_saturday = now + timedelta(days=days_until_saturday)
    return next_saturday.replace(hour=23, minute=0, second=0, microsecond=0)


def get_status_counts():
    """Get counts of listings in each status for the dashboard."""
    counts = {}
    for status in ['draft', 'scheduled', 'listed', 'ended_sold', 'paid', 'shipped']:
        counts[status] = Listing.query.filter_by(status=status).count()
    return counts


@app.route('/')
def index():
    """Dashboard showing overview and action items."""
    counts = get_status_counts()

    # Items needing action
    drafts = Listing.query.filter_by(status='draft').all()
    sold_unpaid = Listing.query.filter_by(status='ended_sold').all()
    paid_unshipped = Listing.query.filter_by(status='paid').all()
    active = Listing.query.filter_by(status='listed').all()

    next_end_time = get_next_saturday_11pm()

    return render_template('index.html',
                           counts=counts,
                           drafts=drafts,
                           sold_unpaid=sold_unpaid,
                           paid_unshipped=paid_unshipped,
                           active=active,
                           next_end_time=next_end_time)


@app.route('/cards')
def list_cards():
    """List all cards."""
    cards = Card.query.order_by(Card.created_at.desc()).all()
    return render_template('cards.html', cards=cards)


@app.route('/cards/add', methods=['GET', 'POST'])
def add_card():
    """Add a new card."""
    if request.method == 'POST':
        card_type = request.form['card_type']
        is_graded = request.form.get('is_graded') == 'on'

        card = Card(
            card_type=card_type,
            name=request.form['name'],
            set_name=request.form.get('set_name'),
            card_number=request.form.get('card_number'),
            player_name=request.form.get('player_name'),
            year=request.form.get('year'),
            quantity=int(request.form.get('quantity', 1)),
            starting_bid=float(request.form.get('starting_bid', 0.50)),
            notes=request.form.get('notes'),
            is_graded=is_graded,
        )

        if is_graded:
            card.grading_company = request.form.get('grading_company')
            card.grade = request.form.get('grade')
            card.condition = f"{card.grading_company} {card.grade}"
        else:
            card.condition = request.form['condition']

        db.session.add(card)
        db.session.commit()

        # Automatically create a draft listing
        listing = Listing(
            card_id=card.id,
            status='draft',
            scheduled_end_time=get_next_saturday_11pm()
        )
        db.session.add(listing)
        db.session.commit()

        flash(f'Card added: {card.title()}', 'success')
        return redirect(url_for('list_cards'))

    return render_template('add_card.html')


@app.route('/cards/<int:card_id>/edit', methods=['GET', 'POST'])
def edit_card(card_id):
    """Edit an existing card."""
    card = Card.query.get_or_404(card_id)

    if request.method == 'POST':
        card.card_type = request.form['card_type']
        card.name = request.form['name']
        card.set_name = request.form.get('set_name')
        card.card_number = request.form.get('card_number')
        card.player_name = request.form.get('player_name')
        card.year = request.form.get('year')
        card.quantity = int(request.form.get('quantity', 1))
        card.starting_bid = float(request.form.get('starting_bid', 0.50))
        card.notes = request.form.get('notes')
        card.is_graded = request.form.get('is_graded') == 'on'

        if card.is_graded:
            card.grading_company = request.form.get('grading_company')
            card.grade = request.form.get('grade')
            card.condition = f"{card.grading_company} {card.grade}"
        else:
            card.condition = request.form['condition']

        db.session.commit()
        flash(f'Card updated: {card.title()}', 'success')
        return redirect(url_for('list_cards'))

    return render_template('edit_card.html', card=card)


@app.route('/listings/<int:listing_id>/status', methods=['POST'])
def update_listing_status(listing_id):
    """Manually update a listing's status."""
    listing = Listing.query.get_or_404(listing_id)
    new_status = request.form['status']

    listing.status = new_status

    if new_status == 'paid':
        # Create order record if doesn't exist
        if not listing.order:
            order = Order(listing_id=listing.id, payment_status='paid', paid_at=datetime.utcnow())
            db.session.add(order)

    if new_status == 'shipped':
        if listing.order:
            listing.order.shipped_at = datetime.utcnow()

    db.session.commit()
    flash(f'Listing status updated to: {new_status}', 'success')
    return redirect(url_for('index'))


@app.route('/report')
def daily_report():
    """Generate daily action report."""
    today = datetime.now(EASTERN).date()

    report = {
        'generated_at': datetime.now(EASTERN),
        'drafts_ready': Listing.query.filter_by(status='draft').count(),
        'active_auctions': Listing.query.filter_by(status='listed').all(),
        'awaiting_payment': Listing.query.filter_by(status='ended_sold').all(),
        'needs_shipping': Listing.query.filter_by(status='paid').all(),
        'recently_shipped': Listing.query.filter_by(status='shipped').all(),
    }

    # Calculate totals
    report['active_count'] = len(report['active_auctions'])
    report['payment_count'] = len(report['awaiting_payment'])
    report['shipping_count'] = len(report['needs_shipping'])

    return render_template('report.html', report=report)


@app.route('/cards/<int:card_id>/delete', methods=['POST'])
def delete_card(card_id):
    """Delete a card and its listing."""
    card = Card.query.get_or_404(card_id)

    # Only allow deletion if listing is still in draft
    if card.listing and card.listing.status != 'draft':
        flash('Cannot delete card with active or completed listing', 'error')
        return redirect(url_for('list_cards'))

    if card.listing:
        db.session.delete(card.listing)

    db.session.delete(card)
    db.session.commit()
    flash('Card deleted', 'success')
    return redirect(url_for('list_cards'))


@app.route('/api/upload-image', methods=['POST'])
def upload_image():
    """Handle image upload without condition check."""
    if 'image' not in request.files:
        return jsonify({'error': 'No image provided'}), 400

    file = request.files['image']
    side = request.form.get('side', 'front')  # 'front' or 'back'

    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{side}_{file.filename}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        # Auto-crop the card from the scan
        auto_crop_card(filepath)

        return jsonify({
            'success': True,
            'filename': filename,
            'filepath': filepath
        })

    return jsonify({'error': 'Invalid file type'}), 400


@app.route('/api/check-condition', methods=['POST'])
def check_condition():
    """Upload image and check condition using Claude API."""
    if 'image' not in request.files:
        return jsonify({'error': 'No image provided'}), 400

    file = request.files['image']
    side = request.form.get('side', 'front')
    card_type = request.form.get('card_type', 'trading card')
    selected_condition = request.form.get('condition', '')

    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not file or not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type'}), 400

    # Save the file
    filename = secure_filename(f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{side}_{file.filename}")
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    # Auto-crop the card from the scan
    auto_crop_card(filepath)

    # Check if API key is configured
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        return jsonify({
            'success': True,
            'filename': filename,
            'filepath': filepath,
            'condition_check': None,
            'warning': 'ANTHROPIC_API_KEY not configured. Image saved but condition not checked.'
        })

    # Read and encode the image
    with open(filepath, 'rb') as f:
        image_data = base64.standard_b64encode(f.read()).decode('utf-8')

    # Determine media type
    ext = filename.rsplit('.', 1)[1].lower()
    media_type = 'image/jpeg' if ext in ('jpg', 'jpeg') else f'image/{ext}'
    if ext in ('tif', 'tiff'):
        media_type = 'image/tiff'

    # Build prompt based on card type
    if card_type == 'sports':
        condition_scale = "NM (Near Mint), EX (Excellent), VG (Very Good), G (Good), P (Poor)"
    else:
        condition_scale = "NM (Near Mint), LP (Lightly Played), MP (Moderately Played), HP (Heavily Played), DMG (Damaged)"

    prompt = f"""Analyze this {card_type} trading card image ({side} of card) for condition assessment.

The seller has selected condition: {selected_condition if selected_condition else 'not yet selected'}

Using the standard condition scale for {card_type} cards: {condition_scale}

Please assess:
1. Corners - any whitening, dings, or wear?
2. Edges - any whitening, chipping, or roughness?
3. Surface - any scratches, print defects, staining, or creases?
4. Centering - estimate the centering (e.g., 60/40, 55/45)

Then provide:
- Your estimated condition grade
- If the seller's selected condition seems accurate, too generous, or too conservative
- Any specific issues a buyer might notice

Be concise and direct. Focus on what matters for selling."""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ]
        )

        assessment = response.content[0].text

        return jsonify({
            'success': True,
            'filename': filename,
            'filepath': filepath,
            'condition_check': assessment
        })

    except Exception as e:
        return jsonify({
            'success': True,
            'filename': filename,
            'filepath': filepath,
            'condition_check': None,
            'error': f'Condition check failed: {str(e)}'
        })


# Create tables on startup
with app.app_context():
    db.create_all()


if __name__ == '__main__':
    app.run(debug=True, port=5000)
