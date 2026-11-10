import os
import sys
import time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api.models import OutboxJob, Order

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://fulfillops_user:secret_password@localhost:5433/fulfillops_db")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def process_jobs():
    print("Worker started, watching for outbox jobs...")
    while True:
        session = SessionLocal()
        try:
            # TEAMMATE 2 TODO: 
            # 1. Use SELECT ... FOR UPDATE SKIP LOCKED to grab a 'pending' job.
            # 2. Change order status to 'completed'
            # 3. Change job status to 'completed'
            # 4. Implement retries if something fails!
            pass
        except Exception as e:
            print(f"Worker error: {e}")
            session.rollback()
        finally:
            session.close()
        
        time.sleep(1) # Prevent CPU spinning

if __name__ == "__main__":
    process_jobs()