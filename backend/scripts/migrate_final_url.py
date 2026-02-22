import sys
import os
from sqlalchemy.orm import Session

# Add the current directory to sys.path to import app modules
sys.path.append(os.path.join(os.getcwd(), 'backend'))
sys.path.append(os.getcwd())

from app.db.database import SessionLocal, engine, Base
from app.db.models import Project
from app.core.config import settings

from sqlalchemy import text

def migrate():
    # Attempt to create tables (this adds the missing final_video_url column if it doesn't exist)
    print("Checking database schema...")
    # SQLAlchemy create_all doesn't add missing columns to existing tables for SQLite
    
    db = SessionLocal()
    try:
        # Manually add the column if it doesn't exist
        try:
            db.execute(text("ALTER TABLE projects ADD COLUMN final_video_url VARCHAR"))
            db.commit()
            print("Added final_video_url column to projects table.")
        except Exception as e:
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                print("Column final_video_url already exists.")
            else:
                print(f"Note: Could not add column via ALTER TABLE: {e}")
                db.rollback()

        # Retroactively fill final_video_url for finished projects
        finished_projects = db.query(Project).filter(Project.status == "finished", Project.final_video_url == None).all()
        print(f"Found {len(finished_projects)} finished projects with missing URL.")
        
        for project in finished_projects:
            final_filename = f"{project.id}.mp4"
            final_path = os.path.join(settings.OUTPUT_DIR, final_filename)
            if os.path.exists(final_path):
                project.final_video_url = f"/output/{final_filename}"
                print(f"Updated project {project.id} with url {project.final_video_url}")
            else:
                # Try the other filename format found in manager.py
                final_filename_mgr = f"{project.id}_final.mp4"
                final_path_mgr = os.path.join(settings.OUTPUT_DIR, final_filename_mgr)
                if os.path.exists(final_path_mgr):
                    project.final_video_url = f"/output/{final_filename_mgr}"
                    print(f"Updated project {project.id} with url {project.final_video_url} (manager format)")
        
        db.commit()
        print("Migration complete.")
    finally:
        db.close()

if __name__ == "__main__":
    migrate()
