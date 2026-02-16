from faster_whisper import WhisperModel
import os

# Initialize model (download on first run)
# 'small' is a good balance. 'medium' or 'large-v3' for better accuracy if GPU available.
# We will check for CUDA availability.
import torch

device = "cuda" if torch.cuda.is_available() else "cpu"
compute_type = "float16" if device == "cuda" else "int8"

model_size = "small" # Configurable?

print(f"Loading Whisper model '{model_size}' on {device} with {compute_type}...")
model = WhisperModel(model_size, device=device, compute_type=compute_type)

def transcribe_audio(file_path: str, language: str = None) -> list:
    """
    Transcribes audio file.
    Returns a list of segments: {"start": float, "end": float, "text": str}
    """
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
