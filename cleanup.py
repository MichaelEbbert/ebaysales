"""
Cleanup script for old card images.
Deletes images for orders that shipped more than 90 days ago.

Run manually or schedule with Windows Task Scheduler:
    python cleanup.py

Options:
    --dry-run    Show what would be deleted without actually deleting
    --days N     Override the 90-day default
"""

import os
import sys
from datetime import datetime, timedelta

# Add the app directory to path
sys.path.insert(0, os.path.dirname(__file__))

from app import app, db
from models import Card, Listing, Order


def cleanup_old_images(days=90, dry_run=False):
    """Delete images for cards where shipping completed more than N days ago."""

    cutoff_date = datetime.utcnow() - timedelta(days=days)

    with app.app_context():
        # Find orders shipped more than N days ago
        old_orders = Order.query.filter(
            Order.shipped_at.isnot(None),
            Order.shipped_at < cutoff_date
        ).all()

        if not old_orders:
            print(f"No orders shipped before {cutoff_date.strftime('%Y-%m-%d')}. Nothing to clean up.")
            return

        files_deleted = 0
        files_not_found = 0
        cards_processed = 0

        uploads_folder = os.path.join(os.path.dirname(__file__), 'uploads')

        for order in old_orders:
            listing = order.listing
            if not listing:
                continue

            card = listing.card
            if not card:
                continue

            cards_processed += 1

            # Check for front image
            if card.image_front:
                filepath = os.path.join(uploads_folder, card.image_front)
                if os.path.exists(filepath):
                    if dry_run:
                        print(f"[DRY RUN] Would delete: {card.image_front}")
                    else:
                        os.remove(filepath)
                        print(f"Deleted: {card.image_front}")
                    files_deleted += 1
                else:
                    files_not_found += 1

                # Clear the path in database
                if not dry_run:
                    card.image_front = None

            # Check for back image
            if card.image_back:
                filepath = os.path.join(uploads_folder, card.image_back)
                if os.path.exists(filepath):
                    if dry_run:
                        print(f"[DRY RUN] Would delete: {card.image_back}")
                    else:
                        os.remove(filepath)
                        print(f"Deleted: {card.image_back}")
                    files_deleted += 1
                else:
                    files_not_found += 1

                # Clear the path in database
                if not dry_run:
                    card.image_back = None

        if not dry_run:
            db.session.commit()

        print(f"\n--- Summary ---")
        print(f"Cards processed: {cards_processed}")
        print(f"Files {'would be ' if dry_run else ''}deleted: {files_deleted}")
        if files_not_found:
            print(f"Files not found (already deleted): {files_not_found}")


def cleanup_orphan_uploads(dry_run=False):
    """
    Delete uploaded files that aren't referenced by any card.
    This handles the case where someone uploads multiple times before saving.
    """

    uploads_folder = os.path.join(os.path.dirname(__file__), 'uploads')

    if not os.path.exists(uploads_folder):
        print("Uploads folder doesn't exist.")
        return

    with app.app_context():
        # Get all referenced filenames from the database
        referenced_files = set()
        cards = Card.query.all()
        for card in cards:
            if card.image_front:
                referenced_files.add(card.image_front)
            if card.image_back:
                referenced_files.add(card.image_back)

        # Check all files in uploads folder
        orphans_deleted = 0
        for filename in os.listdir(uploads_folder):
            filepath = os.path.join(uploads_folder, filename)
            if os.path.isfile(filepath) and filename not in referenced_files:
                if dry_run:
                    print(f"[DRY RUN] Would delete orphan: {filename}")
                else:
                    os.remove(filepath)
                    print(f"Deleted orphan: {filename}")
                orphans_deleted += 1

        print(f"\n--- Orphan Cleanup Summary ---")
        print(f"Orphan files {'would be ' if dry_run else ''}deleted: {orphans_deleted}")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Clean up old card images')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be deleted without deleting')
    parser.add_argument('--days', type=int, default=90, help='Days after shipping to keep images (default: 90)')
    parser.add_argument('--orphans-only', action='store_true', help='Only clean up orphan files, not old shipped orders')

    args = parser.parse_args()

    if args.dry_run:
        print("=== DRY RUN MODE - No files will be deleted ===\n")

    if args.orphans_only:
        cleanup_orphan_uploads(dry_run=args.dry_run)
    else:
        cleanup_old_images(days=args.days, dry_run=args.dry_run)
        print()
        cleanup_orphan_uploads(dry_run=args.dry_run)
