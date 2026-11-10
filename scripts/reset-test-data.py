import sys
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api.models import Base, Product, Order, OrderItem, OutboxJob

DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql://fulfillops_user:secret_password@localhost:5433/fulfillops_db"
)

if "prod" in DATABASE_URL.lower() or "fulfillops_db" not in DATABASE_URL:
    print("CRITICAL ERROR: This script can only be run against a clearly labeled test database.")
    sys.exit(1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def reset_and_seed():
    session = SessionLocal()
    try:
        print("Safely wiping existing test data...")

        session.query(OutboxJob).delete()
        session.query(OrderItem).delete()
        session.query(Order).delete()
        session.query(Product).delete()

        print("Seeding mandatory catalog...")
        catalog = [
            Product(sku="KIT-100", unit_price_cents=1299, available=7),
            Product(sku="PART-200", unit_price_cents=599, available=12),
            Product(sku="PACK-300", unit_price_cents=249, available=5),
        ]
        session.add_all(catalog)
        session.commit()
        print("Database successfully seeded for public checker!")
        
    except Exception as e:
        session.rollback()
        print(f"Error during seed: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    reset_and_seed()