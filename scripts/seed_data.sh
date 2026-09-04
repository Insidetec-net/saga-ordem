#!/bin/bash
set -e

echo "Seeding initial data..."
# This script would typically insert standard items or configurations into the database
# We'll use a python one-liner or a separate python script if needed.

cat << 'EOF' > seed.py
import asyncio
from src.infrastructure.database.connection import async_session_factory
from sqlalchemy import text

async def seed():
    async with async_session_factory() as session:
        # Example: insert stock items if table exists
        await session.execute(text("""
            INSERT INTO stock_items (product_id, quantity)
            VALUES 
            ('0ddb78ea-dd54-4d41-813f-ade5dabc2357', 100),
            ('1ddb78ea-dd54-4d41-813f-ade5dabc2358', 50)
            ON CONFLICT DO NOTHING;
        """))
        await session.commit()
    print("Seed data inserted successfully.")

if __name__ == '__main__':
    asyncio.run(seed())
EOF

python3 seed.py
rm seed.py
