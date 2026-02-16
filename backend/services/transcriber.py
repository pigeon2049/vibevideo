from faster_whisper import WhisperModel
import os

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
        model_size = "small"
        models_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models")
        local_model_path = os.path.join(models_dir, model_size)

        if not os.path.exists(models_dir):
            os.makedirs(models_dir)

        try:
            if os.path.exists(local_model_path):
                print(f"Loading local Whisper model from '{local_model_path}' on {device} with {compute_type}...")
                _model = WhisperModel(local_model_path, device=device, compute_type=compute_type)
            else:
                print(f"Loading Whisper model '{model_size}' (downloading if needed) on {device} with {compute_type}...")
                _model = WhisperModel(model_size, device=device, compute_type=compute_type, download_root=models_dir)
        except Exception as e:
            if device == "cuda":
                print(f"CUDA initialization failed: {e}. Falling back to CPU...")
                device = "cpu"
                compute_type = "int8"
                if os.path.exists(local_model_path):
                    _model = WhisperModel(local_model_path, device=device, compute_type=compute_type)
                else:
                    _model = WhisperModel(model_size, device=device, compute_type=compute_type, download_root=models_dir)
            else:
                raise e
        print(f"Whisper model loaded successfully on {device}.")

    return _model

def transcribe_audio(file_path: str, language: str = None) -> list:
    """
    Transcribes audio file.
    Returns a list of segments: {"start": float, "end": float, "text": str}
    """
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

if __name__ == "__main__":
    # Test
    # Create a dummy file or use an existing one if you have
    pass
