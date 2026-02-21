from services import transcriber
import os

def test_segmentation():
    # Use the existing video file for testing
    video_path = r"D:\source\vibe-video\backend\temp\videos\rSohMpT24SI.mp4"
    
    if not os.path.exists(video_path):
        print(f"Error: Video file not found at {video_path}")
        return

    print(f"Starting transcription for {video_path}...")
    try:
        segments = transcriber.transcribe_audio(video_path)
        
        print(f"\nTranscription complete. Found {len(segments)} segments.")
        print("-" * 30)
        for i, seg in enumerate(segments[:20]):  # Print first 20 segments
            print(f"[{seg['start']:.2f} - {seg['end']:.2f}] {seg['text']}")
        print("-" * 30)
        
        # Check for sentence endings
        sentence_enders = {'.', '!', '?', '。', '！', '？'}
        total_segments = len(segments)
        ending_with_punctuation = sum(1 for seg in segments if seg['text'][-1] in sentence_enders)
        
        print(f"Segments ending with punctuation: {ending_with_punctuation}/{total_segments} ({ending_with_punctuation/total_segments:.1%})")
        
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    test_segmentation()
