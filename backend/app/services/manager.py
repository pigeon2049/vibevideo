import logging
import json
import os
import shutil
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from app.db.models import Project, Segment
from app.services.transcription_service import transcription_service
from app.services.translation_service import translation_service
from app.services.tts_service import tts_service
from app.services.audio_service import audio_service
from app.core.config import settings

logger = logging.getLogger("vibe-video.manager")

class ProjectManager:
    def __init__(self):
        pass

    def get_project(self, db: Session, project_id: str) -> Optional[Project]:
        return db.query(Project).filter(Project.id == project_id).first()

    def create_project(self, db: Session, video_path: str) -> Project:
        # Check for existing project with same video path
        existing = db.query(Project).filter(Project.video_path == video_path).first()
        if existing:
            return existing
            
        project = Project(video_path=video_path, status="idle")
        db.add(project)
        db.commit()
        db.refresh(project)
        return project

    async def run_transcription(self, db: Session, project_id: str, resume: bool = True):
        project = self.get_project(db, project_id)
        if not project:
            raise ValueError("Project not found")

        project.status = "transcribing"
        db.commit()

        resume_start = 0.0
        if resume and project.segments:
            resume_start = project.segments[-1].end_time

        audio_path = await transcription_service.extract_audio(project.video_path, start_time=resume_start)
        logger.info(f"Starting transcription for project {project_id}, audio: {audio_path}")
        try:
            segments = await transcription_service.transcribe(audio_path, resume_start=resume_start)
            logger.info(f"Transcription completed for project {project_id}, segments found: {len(segments)}")
        except Exception as e:
            logger.error(f"Error during transcription call in manager: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise

        for s in segments:
            new_segment = Segment(
                id=s["id"],
                project_id=project_id,
                start_time=s["start"],
                end_time=s["end"],
                text_original=s["text"]
            )
            db.add(new_segment)
        
        project.status = "reviewing"
        db.commit()
        return segments

    async def run_translation(self, db: Session, project_id: str, target_lang: str):
        project = self.get_project(db, project_id)
        if not project:
            raise ValueError("Project not found")

        project.status = "translating"
        project.target_language = target_lang
        db.commit()

        untranslated = db.query(Segment).filter(
            Segment.project_id == project_id,
            Segment.text_translated == None
        ).order_by(Segment.start_time).all()

        segments_data = [
            {"id": s.id, "start": s.start_time, "end": s.end_time, "text": s.text_original}
            for s in untranslated
        ]

        async for chunk in translation_service.translate_segments_stream(segments_data, target_lang):
            for translated_seg in chunk:
                db_seg = db.query(Segment).filter(Segment.id == translated_seg["id"]).first()
                if db_seg:
                    db_seg.text_translated = translated_seg["text"]
            db.commit()
            yield chunk

        # Check if all done
        remaining = db.query(Segment).filter(
            Segment.project_id == project_id,
            Segment.text_translated == None
        ).count()
        
        if remaining == 0:
            project.status = "translated"
            db.commit()

    async def run_dubbing(self, db: Session, project_id: str, voice: str, bg_volume: float = 0.1):
        project = self.get_project(db, project_id)
        if not project:
            raise ValueError("Project not found")

        project.status = "dubbing"
        db.commit()

        # Handle default voice selection
        if not voice or (isinstance(voice, str) and voice.lower() == "default"):
            if project.target_language == "zh":
                voice = tts_service.default_voice_zh
            else:
                voice = tts_service.default_voice_en
            logger.info(f"[MANAGER] Using default voice: '{voice}' for language: '{project.target_language}'")
        else:
            logger.info(f"[MANAGER] Using requested voice: '{voice}'")

        segments = db.query(Segment).filter(Segment.project_id == project_id).order_by(Segment.start_time).all()
        
        # Group segments into paragraphs for more natural TTS
        segments_data = [
            {
                "id": s.id,
                "start": s.start_time,
                "end": s.end_time,
                "text": s.text_translated or s.text_original
            }
            for s in segments
        ]
        
        paragraphs = []
        if segments_data:
            current_para = {
                "id": f"para_{segments_data[0]['id']}", 
                "start": segments_data[0]["start"], 
                "end": segments_data[0]["end"], 
                "texts": [segments_data[0]["text"]],
                "segment_ids": [segments_data[0]["id"]]
            }
            for i in range(1, len(segments_data)):
                seg = segments_data[i]
                gap = seg["start"] - current_para["end"]
                
                # Simple rule: if gap is small and no sentence break, merge
                last_text = current_para["texts"][-1].strip()
                ends_with_break = last_text and last_text[-1] in ".。!?！？\n"
                
                if gap <= 1.0 and not ends_with_break:
                    current_para["texts"].append(seg["text"])
                    current_para["end"] = seg["end"]
                    current_para["segment_ids"].append(seg["id"])
                else:
                    paragraphs.append(current_para)
                    current_para = {
                        "id": f"para_{seg['id']}", 
                        "start": seg["start"], 
                        "end": seg["end"], 
                        "texts": [seg["text"]],
                        "segment_ids": [seg["id"]]
                    }
            paragraphs.append(current_para)

        for p in paragraphs:
            p["text"] = " ".join(p["texts"])

        logger.info(f"Generating TTS for {len(paragraphs)} paragraphs (grouped from {len(segments)} segments)")
        
        # Yield initial state
        initial_paras = [{"id": p["id"], "text": p["text"], "start": p["start"]} for p in paragraphs]
        yield {"step": "tts", "current": 0, "total": len(paragraphs), "paragraphs": initial_paras}

        paragraphs_with_audio = []
        for i, para in enumerate(paragraphs):
            text = para["text"]
            if tts_service.is_speakable(text):
                # generate_speech handles caching internally
                audio_path = await tts_service.generate_speech(text, voice)
                para["audio_file"] = audio_path
                
                # Update DB for each segment in this paragraph
                for seg_id in para["segment_ids"]:
                    db_seg = db.query(Segment).filter(Segment.id == seg_id).first()
                    if db_seg:
                        db_seg.tts_audio_path = audio_path
                db.commit()
            else:
                logger.info(f"[MANAGER] Skipping non-speakable paragraph: '{text[:20]}...'")
                para["audio_file"] = None
            
            paragraphs_with_audio.append(para)
            
            # Yield progress for each paragraph
            audio_url = f"/audio/{os.path.basename(para['audio_file'])}" if para["audio_file"] else None
            yield {
                "step": "tts", 
                "current": i + 1, 
                "total": len(paragraphs), 
                "paragraph": {
                    "id": para["id"],
                    "text": para["text"],
                    "start": para["start"],
                    "audio_url": audio_url
                }
            }

        # Audio processing steps
        yield {"step": "isolate"}
        logger.info("Starting audio processing: isolation")
        orig_audio = await audio_service.isolate_audio(project.video_path)
        
        yield {"step": "separate"}
        logger.info("Starting audio processing: separation")
        separated = await audio_service.separate_vocals(orig_audio)
        
        yield {"step": "merge"}
        logger.info("Starting audio processing: merge")
        
        # Generate SRT (simple implementation)
        # Using segments_data which has the translated texts
        srt_content = ""
        for i, s in enumerate(segments_data):
            start_str = self._format_timestamp(s["start"])
            end_str = self._format_timestamp(s["end"])
            srt_content += f"{i+1}\n{start_str} --> {end_str}\n{s['text']}\n\n"
        
        srt_path = settings.TEMP_DIR / f"{project_id}.srt"
        srt_path.write_text(srt_content, encoding="utf-8")

        # Merge
        final_video_temp = await audio_service.merge_audio_video(
            project.video_path,
            separated["background"],
            paragraphs_with_audio,
            bg_volume=bg_volume,
            subtitle_path=str(srt_path)
        )
        
        # Moves to a final deterministic path
        final_filename = f"{project_id}_final.mp4"
        final_video = settings.OUTPUT_DIR / final_filename
        if os.path.exists(final_video):
            os.remove(final_video)
        import shutil
        shutil.move(final_video_temp, final_video)

        project.status = "finished"
        project.final_video_url = f"/output/{final_filename}"
        db.commit()
        
        yield {
            "step": "done",
            "url": project.final_video_url
        }

    def _format_timestamp(self, seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

project_manager = ProjectManager()
