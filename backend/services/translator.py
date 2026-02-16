from openai import OpenAI
import os
import json
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
load_dotenv(dotenv_path)

# Initialize client (uses OPENAI_API_KEY from env, and OPENAI_BASE_URL if set)
# Default to OpenAI if not set, but user provided specific configuration.
base_url = os.environ.get("OPENAI_BASE_URL")
api_key = os.environ.get("OPENAI_API_KEY")
model_name = os.environ.get("LLM_MODEL", "gpt-4o-mini")

client = None
if api_key:
    client = OpenAI(
        base_url=base_url, 
        api_key=api_key
    )
else:
    print("Warning: OPENAI_API_KEY not found in environment variables. Translation will be disabled.")

def translate_segments(segments, target_language="English"):
    """
    Translates a list of segments to target language.
    Expects segments to be a list of dicts with 'text', 'start', 'end'.
    Returns updated list of segments with 'text' translated.
    """
    if not client:
        print("Translation skipped: OpenAI client not initialized.")
        return segments

    # Extract just the text to save tokens/make it easier for LLM
    texts = [s['text'] for s in segments]
    
    # Prepare the prompt
    system_prompt = f"""You are a professional subtitle translator. 
    Translate the following list of subtitle lines to {target_language}.
    Maintain the tone and context.
    Return ONLY a JSON array of strings, matching the input array length exactly.
    Do not include any other text or markdown formatting.
    """
    
    user_prompt = json.dumps(texts, ensure_ascii=False)
    
    try:
        response = client.chat.completions.create(
            model=model_name, # Use configured model
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"} if "gpt" in model_name or "json" in model_name else None # JSON mode varies by provider
        )
        
        content = response.choices[0].message.content
        # sometimes metrics/markdown might be included despite instructions
        if "```json" in content:
            content = content.replace("```json", "").replace("```", "")
            
        translated_texts = json.loads(content)
        
        # Check if it's a list (some models might wrap it in a dict like {"translations": [...]})
        if isinstance(translated_texts, dict):
            # Try to report the first list found
            for key, value in translated_texts.items():
                if isinstance(value, list):
                    translated_texts = value
                    break
        
        if len(translated_texts) != len(segments):
            print(f"Warning: Mismatch in translation count. Input: {len(segments)}, Output: {len(translated_texts)}")
        
        # Update segments
        translated_segments = []
        for i, segment in enumerate(segments):
            translated_text = translated_texts[i] if i < len(translated_texts) else segment['text']
            translated_segments.append({
                "start": segment["start"],
                "end": segment["end"],
                "text": translated_text
            })
            
        return translated_segments

    except Exception as e:
        error_msg = str(e).lower()
        if "unauthorized" in error_msg:
            print(f"Translation error: Unauthorized. Please check your Ollama API key and BASE_URL in .env")
        else:
            print(f"Translation error: {e}")
        return segments # Return original on failure

