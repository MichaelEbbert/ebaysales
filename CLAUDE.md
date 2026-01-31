# eBay Trading Card Auction Manager

## Project Overview
A streamlined application for managing eBay trading card auctions from listing through shipping.

## Core Requirements

### Card Types Supported
- Sports cards (Baseball, Basketball, Football, Hockey, etc.)
- Magic: The Gathering (MTG)
- Pokemon

### Condition Grading Conventions
- **Sports Cards**: Raw (NM, EX, VG, G, P) or Graded (PSA, BGS, SGC, CGC with numeric grade)
- **MTG & Pokemon**: NM (Near Mint), LP (Lightly Played), MP (Moderately Played), HP (Heavily Played), DMG (Damaged)

### Auction Settings
- **Style**: Auction format only (no Buy It Now)
- **End Time Target**: 11:00 PM Eastern on Saturdays
- **Starting Bid**: $0.50 default (lowest insertion fee tier), configurable for high-value items
- **Quantity**: Support 1x, 2x, 3x, 4x of the same card in one listing

### Workflow States
1. **Draft** - Item entered but not posted
2. **Listed** - Active auction on eBay
3. **Ended - Unsold** - Auction closed with no bids
4. **Ended - Sold** - Auction closed with winning bid
5. **Paid** - Buyer has paid
6. **Shipped** - Label printed, marked as shipped
7. **Complete** - Delivered/no further action needed

### Daily Report
- Items needing to be listed (drafts ready to post)
- Active auctions (with current bid info)
- Sold items awaiting payment
- Paid items needing shipping
- Recently shipped items

## Technical Decisions

### Stack
- **UI**: Web App (local browser-based at http://localhost:5000)
- **Backend**: Python + Flask
- **Frontend**: Simple HTML/CSS/JS (no framework)
- **Database**: SQLite (single file, portable, no server)
- **Shipping**: eBay's built-in labels (no external service needed)

### Scanning Setup
- **Scanner**: Flatbed scanner (user's existing document scanner)
- **DPI**: 600 DPI recommended
- **Scan size**: Use "Auto" - app handles cropping
- **Card placement**: Top-left corner, flush to scanner edge
- **Sleeves**: Cards scanned in penny sleeves

### Auto-Crop Settings (600 DPI)
The app automatically crops scans to the card dimensions:
- Card size: 2.5" x 3.5" (1500 x 2100 pixels)
- Penny sleeve adds: 3mm left/right/bottom, 5mm top
- 5px cushion added to right/bottom edges
- Source file can be deleted after upload (app keeps its own copy)

### Image Condition Checking
- Two upload buttons: "Upload" (free) and "Upload & Check Condition" (uses API)
- Condition check uses Claude Sonnet via Anthropic API
- Compares your selected grade against visual assessment
- Flags corners, edges, surface issues, and centering
- **Cost**: ~$0.003 per image (about 3 checks per penny, or ~330 checks per dollar)
  - Based on actual usage: ~500 input tokens + ~70 output tokens per check
  - Sonnet pricing: $3/M input, $15/M output

### UI Guidelines
- No placeholder text in any form fields

### Form Field Notes
- **Additional Details** (Sports): Use for extras like "RC", "/199", "Refractor", "Auto", "SP"
- **Additional Details** (MTG/Pokemon): The actual card name (e.g., "Charizard", "Black Lotus")
- **Player Name / Year**: Sports cards only
- **Set / Product**: e.g., "Topps Chrome", "Base Set", "Prizm"
- **Card Number**: e.g., "175", "4/102" (hidden for MTG)
- **Foil**: MTG and Pokemon only (Non-Foil / Foil)
- **Public Notes**: Shown in auction description
- **Private Notes**: Internal only (cost tracking, inventory location, etc.)

### Listing Title Conventions
- **MTG cards**: Always start with "MTG" prefix (e.g., "MTG Revised Underground Sea Dual Land x1 LP")
- **Dual lands**: Revised/Unlimited/Beta/Alpha dual lands automatically include "Dual Land" in title
- **Quantity**: Shown as "x1", "x2", etc.

### Shipping Options
Buyer-selectable at checkout, configured in Settings:
| Option | Method | Tracking | Insurance | Default Price |
|--------|--------|----------|-----------|---------------|
| Economy | Stamped #10 envelope | No | No | $1.00 |
| Standard | Bubble mailer | Yes | No | $4.50 |
| Insured (up to $100) | Bubble mailer | Yes | Yes | $6.50 |
| Insured (up to $250) | Bubble mailer | Yes | Yes | $8.50 |

Thresholds for shipping recommendations configurable in Settings page.

### API Accounts Required
1. **Anthropic API** (console.anthropic.com) - For condition checking
   - Pay-as-you-go, ~$0.003 per image (~330 checks per dollar)
   - Key stored in `.env` file
   - Check usage at console.anthropic.com → Usage

2. **eBay Developer Account** (developer.ebay.com) - For posting/syncing
   - Free to register
   - Requires approval (1+ days)
   - Status: Pending approval

## Setup Instructions

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Create `.env` file (copy from `.env.example`):
   ```
   copy .env.example .env
   ```

3. Add your Anthropic API key to `.env` (for condition checking)

4. Run the app:
   ```
   python app.py
   ```

5. Open http://localhost:5000

## Maintenance

### Image Cleanup
Run periodically to delete old images:
```
# Preview what would be deleted
python cleanup.py --dry-run

# Delete images for orders shipped 90+ days ago
python cleanup.py

# Change retention period
python cleanup.py --days 60

# Only clean orphan uploads (duplicates from re-uploading)
python cleanup.py --orphans-only
```

## Project Status

### Completed
- [x] Flask app structure with SQLite database
- [x] Card, Listing, Order models
- [x] Dashboard with status counts and action items
- [x] Add/Edit/Delete cards
- [x] Daily report page
- [x] Image upload with auto-crop (fixed dimensions for penny-sleeved cards)
- [x] Claude Vision API condition checking
- [x] Cleanup script for old images (90 days after shipping)
- [x] Auction preview page with auto-generated title and description
- [x] Buyer-selectable shipping options with packing instructions
- [x] Settings page for shipping thresholds and pricing
- [x] Foil support for MTG and Pokemon cards
- [x] Public/Private notes separation

### Pending (waiting on eBay developer account approval)
- [ ] eBay API integration
- [ ] Post listings to eBay
- [ ] Sync auction status from eBay
- [ ] Print shipping labels via eBay

### Future Enhancements
- [ ] Batch listing multiple cards
- [ ] Relisting unsold items
- [ ] Sales analytics/reporting

## Schedule Notes
- **Saturday 11pm ET**: Auctions end
- **Sunday**: Packaging day
- **Monday**: Mail goes out
- Reports can be run multiple times per day
