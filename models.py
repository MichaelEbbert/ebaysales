from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Card(db.Model):
    __tablename__ = 'cards'

    id = db.Column(db.Integer, primary_key=True)
    card_type = db.Column(db.String(20), nullable=False)  # 'sports', 'mtg', 'pokemon'
    name = db.Column(db.String(200), nullable=False)
    set_name = db.Column(db.String(100))  # Set or year
    card_number = db.Column(db.String(50))  # Card number in set
    player_name = db.Column(db.String(100))  # For sports cards
    year = db.Column(db.String(10))  # For sports cards
    condition = db.Column(db.String(20), nullable=False)  # NM, LP, PSA 9, etc.
    is_graded = db.Column(db.Boolean, default=False)
    grading_company = db.Column(db.String(20))  # PSA, BGS, SGC
    grade = db.Column(db.String(10))  # 9, 9.5, 10, etc.
    quantity = db.Column(db.Integer, default=1)  # 1x, 2x, 3x, 4x
    starting_bid = db.Column(db.Float, default=0.50)
    notes = db.Column(db.Text)
    image_front = db.Column(db.String(500))  # Path to front scan
    image_back = db.Column(db.String(500))  # Path to back scan
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    listing = db.relationship('Listing', backref='card', uselist=False)

    def condition_display(self):
        """Return properly formatted condition string."""
        if self.is_graded:
            return f"{self.grading_company} {self.grade}"
        return self.condition

    def title(self):
        """Generate eBay listing title."""
        parts = []
        if self.quantity > 1:
            parts.append(f"{self.quantity}x")

        if self.card_type == 'sports':
            if self.year:
                parts.append(self.year)
            if self.set_name:
                parts.append(self.set_name)
            if self.player_name:
                parts.append(self.player_name)
            if self.card_number:
                parts.append(f"#{self.card_number}")
        else:
            # MTG or Pokemon
            parts.append(self.name)
            if self.set_name:
                parts.append(f"[{self.set_name}]")
            if self.card_number:
                parts.append(f"#{self.card_number}")

        parts.append(self.condition_display())
        return " ".join(parts)


class Listing(db.Model):
    __tablename__ = 'listings'

    id = db.Column(db.Integer, primary_key=True)
    card_id = db.Column(db.Integer, db.ForeignKey('cards.id'), nullable=False)
    ebay_listing_id = db.Column(db.String(50))  # Populated after posting to eBay
    status = db.Column(db.String(20), default='draft')
    # Statuses: draft, scheduled, listed, ended_unsold, ended_sold, paid, shipped, complete

    scheduled_end_time = db.Column(db.DateTime)  # Target: Saturday 11pm ET
    actual_start_time = db.Column(db.DateTime)
    actual_end_time = db.Column(db.DateTime)

    current_bid = db.Column(db.Float)
    winning_bid = db.Column(db.Float)
    ebay_fees = db.Column(db.Float)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    order = db.relationship('Order', backref='listing', uselist=False)


class Order(db.Model):
    __tablename__ = 'orders'

    id = db.Column(db.Integer, primary_key=True)
    listing_id = db.Column(db.Integer, db.ForeignKey('listings.id'), nullable=False)
    ebay_order_id = db.Column(db.String(50))

    buyer_username = db.Column(db.String(100))
    buyer_name = db.Column(db.String(200))
    shipping_address = db.Column(db.Text)

    sale_price = db.Column(db.Float)
    shipping_cost = db.Column(db.Float)
    total_price = db.Column(db.Float)

    payment_status = db.Column(db.String(20))  # pending, paid
    paid_at = db.Column(db.DateTime)

    tracking_number = db.Column(db.String(100))
    shipping_carrier = db.Column(db.String(50))
    shipped_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
