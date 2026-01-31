from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Card(db.Model):
    __tablename__ = 'cards'
    __table_args__ = {'sqlite_autoincrement': True}

    id = db.Column(db.Integer, primary_key=True)
    card_type = db.Column(db.String(20), nullable=False)  # 'sports', 'mtg', 'pokemon'
    name = db.Column(db.String(200))  # Additional details - optional
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
    notes = db.Column(db.Text)  # Public notes - shown in auction description
    private_notes = db.Column(db.Text)  # Private notes - internal use only
    foil = db.Column(db.String(20))  # 'foil' or 'non-foil' for MTG/Pokemon
    image_front = db.Column(db.String(500))  # Path to front scan
    image_back = db.Column(db.String(500))  # Path to back scan
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    listing = db.relationship('Listing', backref='card', uselist=False)

    def condition_display(self):
        """Return properly formatted condition string."""
        if self.is_graded:
            return f"{self.grading_company} {self.grade}"
        return self.condition

    # Revised/Unlimited/Beta dual lands
    DUAL_LANDS = [
        'Underground Sea', 'Volcanic Island', 'Tropical Island', 'Tundra',
        'Savannah', 'Scrubland', 'Badlands', 'Taiga', 'Plateau', 'Bayou'
    ]
    DUAL_LAND_SETS = ['Revised', 'Unlimited', 'Beta', 'Alpha']

    def title(self):
        """Generate eBay listing title."""
        parts = []

        if self.card_type == 'mtg':
            parts.append('MTG')

        if self.card_type == 'sports':
            if self.year:
                parts.append(self.year)
            if self.set_name:
                parts.append(self.set_name)
            if self.player_name:
                parts.append(self.player_name)
            if self.card_number:
                parts.append(f"#{self.card_number}")
            if self.name:
                parts.append(self.name)
        else:
            # MTG or Pokemon
            if self.set_name:
                parts.append(self.set_name)
            if self.name:
                parts.append(self.name)
            # Add "Dual Land" for Revised/Unlimited/Beta/Alpha dual lands
            if self.card_type == 'mtg' and self.set_name in self.DUAL_LAND_SETS:
                if self.name in self.DUAL_LANDS:
                    parts.append('Dual Land')

        # Quantity
        parts.append(f"x{self.quantity}")

        # Condition
        parts.append(self.condition_display())

        return " ".join(parts)

    # Shipping options available to buyers
    SHIPPING_OPTIONS = [
        {
            'name': 'Economy',
            'method': 'Stamped envelope',
            'tracking': False,
            'insurance': False,
            'price': 1.00,
            'cost': 0.75,
            'label_size': None,  # No label, uses stamp
            'packing': '#10 envelope with top loader and cardboard stiffener'
        },
        {
            'name': 'Standard',
            'method': 'Bubble mailer',
            'tracking': True,
            'insurance': False,
            'price': 4.50,
            'cost': 4.00,
            'label_size': '4" x 6"',
            'packing': 'Bubble mailer with top loader and ding protector'
        },
        {
            'name': 'Insured (up to $100)',
            'method': 'Bubble mailer',
            'tracking': True,
            'insurance': True,
            'insurance_limit': 100,
            'price': 6.50,
            'cost': 4.90,
            'label_size': '4" x 6"',
            'packing': 'Bubble mailer with top loader and ding protector'
        },
        {
            'name': 'Insured (up to $250)',
            'method': 'Bubble mailer',
            'tracking': True,
            'insurance': True,
            'insurance_limit': 250,
            'price': 8.50,
            'cost': 5.75,
            'label_size': '4" x 6"',
            'packing': 'Bubble mailer with top loader and ding protector'
        },
    ]

    def generate_description(self, shipping_options=None):
        """Generate eBay listing description."""
        if shipping_options is None:
            shipping_options = self.SHIPPING_OPTIONS

        lines = []

        # Card details
        if self.card_type == 'mtg':
            lines.append(f"Magic: The Gathering - {self.name}")
        elif self.card_type == 'pokemon':
            lines.append(f"Pokemon - {self.name}")
        else:
            if self.player_name:
                lines.append(f"{self.year} {self.set_name} {self.player_name}")
            else:
                lines.append(f"{self.year} {self.set_name}")

        if self.set_name and self.card_type != 'sports':
            lines.append(f"Set: {self.set_name}")

        lines.append(f"Condition: {self.condition_display()}")
        lines.append(f"Quantity: {self.quantity}")

        lines.append("")
        lines.append("The card for sale is the one pictured and described in the title.")
        lines.append("Please see the scans for condition and ask any questions before bidding.")

        if self.notes:
            lines.append("")
            lines.append(f"Notes: {self.notes}")

        # Shipping table
        lines.append("")
        lines.append("--- SHIPPING OPTIONS ---")
        lines.append("")
        lines.append("Option              | Method           | Tracking | Insurance | Price")
        lines.append("--------------------|------------------|----------|-----------|------")
        for opt in shipping_options:
            tracking = "Yes" if opt['tracking'] else "No"
            insurance = "Yes" if opt['insurance'] else "No"
            lines.append(f"{opt['name']:<19} | {opt['method']:<16} | {tracking:<8} | {insurance:<9} | ${opt['price']:.2f}")

        return "\n".join(lines)

    def get_recommended_shipping(self, sale_price=None):
        """Get recommended shipping option based on sale price."""
        price = sale_price or self.starting_bid

        if price >= 100:
            return self.SHIPPING_OPTIONS[3]  # Insured up to $250
        elif price >= 50:
            return self.SHIPPING_OPTIONS[2]  # Insured up to $100
        elif price >= 20:
            return self.SHIPPING_OPTIONS[1]  # Standard tracked
        else:
            return self.SHIPPING_OPTIONS[0]  # Economy


class Listing(db.Model):
    __tablename__ = 'listings'
    __table_args__ = {'sqlite_autoincrement': True}

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
    __table_args__ = {'sqlite_autoincrement': True}

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
