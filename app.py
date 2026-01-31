from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
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
import json
import time

load_dotenv()

SETTINGS_FILE = os.path.join(os.path.dirname(__file__), 'settings.json')


def load_settings():
    """Load settings from JSON file."""
    try:
        with open(SETTINGS_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return get_default_settings()


def save_settings(settings):
    """Save settings to JSON file."""
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=4)


def get_default_settings():
    """Return default settings."""
    return {
        "shipping_options": [
            {"name": "Economy", "method": "Stamped envelope", "tracking": False,
             "insurance": False, "insurance_limit": None, "price": 1.00, "cost": 0.75,
             "label_size": None, "packing": "#10 envelope with top loader and cardboard stiffener"},
            {"name": "Standard", "method": "Bubble mailer", "tracking": True,
             "insurance": False, "insurance_limit": None, "price": 4.50, "cost": 4.00,
             "label_size": "4\" x 6\"", "packing": "Bubble mailer with top loader and ding protector"},
            {"name": "Insured (up to $100)", "method": "Bubble mailer", "tracking": True,
             "insurance": True, "insurance_limit": 100, "price": 6.50, "cost": 4.90,
             "label_size": "4\" x 6\"", "packing": "Bubble mailer with top loader and ding protector"},
            {"name": "Insured (up to $250)", "method": "Bubble mailer", "tracking": True,
             "insurance": True, "insurance_limit": 250, "price": 8.50, "cost": 5.75,
             "label_size": "4\" x 6\"", "packing": "Bubble mailer with top loader and ding protector"},
        ],
        "shipping_thresholds": {
            "economy_max": 19.99,
            "standard_max": 49.99,
            "insured_100_max": 99.99
        }
    }


def get_shipping_options():
    """Get shipping options from settings."""
    settings = load_settings()
    return settings.get('shipping_options', get_default_settings()['shipping_options'])


def get_recommended_shipping(sale_price):
    """Get recommended shipping option based on sale price."""
    settings = load_settings()
    thresholds = settings.get('shipping_thresholds', get_default_settings()['shipping_thresholds'])
    options = settings.get('shipping_options', get_default_settings()['shipping_options'])

    if sale_price >= thresholds['insured_100_max'] + 0.01:
        return options[3] if len(options) > 3 else options[-1]  # Insured $250
    elif sale_price >= thresholds['standard_max'] + 0.01:
        return options[2] if len(options) > 2 else options[-1]  # Insured $100
    elif sale_price >= thresholds['economy_max'] + 0.01:
        return options[1] if len(options) > 1 else options[-1]  # Standard
    else:
        return options[0]  # Economy

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


def get_next_auction_end_time():
    """Calculate the next auction end time (11:00 PM Eastern, at least 120 hours away)."""
    now = datetime.now(EASTERN)
    min_end_time = now + timedelta(hours=120)  # At least 5 days from now

    # Start from today at 11pm and find the next 11pm that's >= 120 hours away
    candidate = now.replace(hour=23, minute=0, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)

    while candidate < min_end_time:
        candidate += timedelta(days=1)

    return candidate


def get_next_saturday_11pm():
    """Calculate the next Saturday at 11:00 PM Eastern (legacy, now uses get_next_auction_end_time)."""
    return get_next_auction_end_time()


def get_status_counts():
    """Get counts of listings in each status for the dashboard."""
    counts = {}
    for status in ['draft', 'scheduled', 'listed', 'ended_sold', 'paid', 'shipped']:
        counts[status] = Listing.query.filter_by(status=status).count()
    return counts


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """Serve uploaded images."""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


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
            private_notes=request.form.get('private_notes'),
            foil=request.form.get('foil'),
            is_graded=is_graded,
            image_front=request.form.get('image_front'),
            image_back=request.form.get('image_back'),
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
        card.private_notes = request.form.get('private_notes')
        card.foil = request.form.get('foil')
        card.is_graded = request.form.get('is_graded') == 'on'

        # Only update images if new ones are provided
        if request.form.get('image_front'):
            card.image_front = request.form.get('image_front')
        if request.form.get('image_back'):
            card.image_back = request.form.get('image_back')

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


@app.route('/listings/<int:listing_id>/preview')
def preview_listing(listing_id):
    """Preview auction details before posting."""
    listing = Listing.query.get_or_404(listing_id)
    card = listing.card

    # Get shipping options and recommendation from settings
    shipping_options = get_shipping_options()
    recommended_shipping = get_recommended_shipping(card.starting_bid)

    return render_template('preview_listing.html',
                           listing=listing,
                           card=card,
                           title=card.title(),
                           description=card.generate_description(shipping_options),
                           shipping_options=shipping_options,
                           recommended_shipping=recommended_shipping)


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

    # Retry logic: 3 attempts with 3 seconds between each
    max_attempts = 3
    last_error = None

    for attempt in range(max_attempts):
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
            last_error = e
            if attempt < max_attempts - 1:
                time.sleep(3)  # Wait 3 seconds before retrying

    return jsonify({
        'success': True,
        'filename': filename,
        'filepath': filepath,
        'condition_check': None,
        'error': f'Condition check failed after {max_attempts} attempts: {str(last_error)}'
    })


@app.route('/settings')
def settings():
    """View and edit application settings."""
    current_settings = load_settings()
    return render_template('settings.html', settings=current_settings)


@app.route('/settings/shipping', methods=['POST'])
def update_shipping_settings():
    """Update shipping settings."""
    current_settings = load_settings()

    # Update thresholds
    current_settings['shipping_thresholds'] = {
        'economy_max': float(request.form.get('economy_max', 19.99)),
        'standard_max': float(request.form.get('standard_max', 49.99)),
        'insured_100_max': float(request.form.get('insured_100_max', 99.99))
    }

    # Update shipping options prices and costs
    for i, opt in enumerate(current_settings['shipping_options']):
        price_key = f'option_{i}_price'
        cost_key = f'option_{i}_cost'
        if price_key in request.form:
            current_settings['shipping_options'][i]['price'] = float(request.form[price_key])
        if cost_key in request.form:
            current_settings['shipping_options'][i]['cost'] = float(request.form[cost_key])

    save_settings(current_settings)
    flash('Shipping settings updated successfully', 'success')
    return redirect(url_for('settings'))


@app.route('/settings/reset', methods=['POST'])
def reset_settings():
    """Reset settings to defaults."""
    save_settings(get_default_settings())
    flash('Settings reset to defaults', 'success')
    return redirect(url_for('settings'))


# Create tables on startup
with app.app_context():
    db.create_all()


if __name__ == '__main__':
    app.run(debug=True, port=5000)
