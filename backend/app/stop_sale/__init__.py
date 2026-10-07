"""Stop sale emails: close static (contracted/wholesale) rates with partners
by email when combined inventory says a date or room type is full.

- rules.py  - which dates/room types qualify, from combined_inventory.db
- store.py  - recipients, settings and send history (stop_sale.db)
- mailer.py - builds and sends one email per recipient over SMTP
"""
