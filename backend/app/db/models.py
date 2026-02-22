import datetime
import uuid
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from .database import Base

def generate_uuid():
    return str(uuid.uuid4())

class Project(Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True, default=generate_uuid)
    video_path = Column(String, index=True)
    status = Column(String, default="idle")  # idle, transcribing, reviewing, translating, translated, dubbing, finished
    target_language = Column(String, default="zh")
    final_video_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    segments = relationship("Segment", back_populates="project", cascade="all, delete-orphan", order_by="Segment.start_time")

class Segment(Base):
    __tablename__ = "segments"

    id = Column(String, primary_key=True, default=generate_uuid)
    project_id = Column(String, ForeignKey("projects.id"))
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)
    text_original = Column(Text, nullable=False)
    text_translated = Column(Text, nullable=True)
    tts_audio_path = Column(String, nullable=True)

    project = relationship("Project", back_populates="segments")
