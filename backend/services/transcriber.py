from faster_whisper import WhisperModel
import os
import gc

# Initialize model (download on first run)
# 'small' is a good balance. 'medium' or 'large-v3' for better accuracy if GPU available.
# We will check for CUDA availability.
import torch

_model = None

def get_model():
    """
    Lazy loader for the Whisper model.
    """
    global _model
    if _model is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"
        
        # Calculate relative path to model
        # __file__ is d:\source\vibe-video\backend\services\transcriber.py
        # root is d:\source\vibe-video
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        model_path = os.path.join(project_root, "models", "large-v3")

        print(f"Loading Whisper model from '{model_path}' on {device} with {compute_type}...")
        try:
            _model = WhisperModel(model_path, device=device, compute_type=compute_type)
        except Exception as e:
            if device == "cuda":
                print(f"CUDA initialization failed: {e}. Falling back to CPU...")
                device = "cpu"
                compute_type = "int8"
                _model = WhisperModel(model_path, device=device, compute_type=compute_type)
            else:
                raise e
        print(f"Whisper model loaded successfully on {device}.")

    return _model

def unload_model():
    """
    Unloads the Whisper model and frees VRAM.
    """
    global _model
    if _model is not None:
        print("Unloading Whisper model to free VRAM...")
        # Deep delete and clear cache
        del _model
        _model = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        print("Whisper model unloaded and VRAM cleared.")

def transcribe_audio(file_path: str, language: str = None) -> list:
    """
    Transcribes audio file.
    Returns a list of segments: {"start": float, "end": float, "text": str}
    """
    try:
        model = get_model()
        segments, info = model.transcribe(file_path, language=language, beam_size=5)

        
        print(f"Detected language '{info.language}' with probability {info.language_probability}")
        
        result = []
        for segment in segments:
            result.append({
                "start": segment.start,
                "end": segment.end,
                "text": segment.text.strip()
            })
            
        return result
    finally:
        unload_model()

if __name__ == "__main__":
    # Test
    # Create a dummy file or use an existing one if you have
    pass
