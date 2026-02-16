from openai import OpenAI, APITimeoutError, APIConnectionError, RateLimitError
import os
import json
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

dotenv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
load_dotenv(dotenv_path)

# Initialize client
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

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((APITimeoutError, APIConnectionError, RateLimitError)),
    reraise=True
)
def fetch_translation_with_retry(system_prompt, user_prompt):
    """
    Fetches translation from OpenAI API with retry logic.
    """
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        response_format={"type": "json_object"} if "gpt" in model_name or "json" in model_name else None,
        timeout=30.0 # 30 seconds timeout
    )
    return response.choices[0].message.content

def translate_segments(segments, target_language="English"):
    """
    Sync wrapper for translate_segments_stream
    """
    translated = []
    for chunk in translate_segments_stream(segments, target_language):
        translated.extend(chunk)
    return translated

def translate_segments_stream(segments, target_language="English", chunk_size=5):
    """
    Translates a list of segments to target language in chunks.
    Yields translated chunks one by one.
    Maintain the tone and context.
    """
    if not client:
        print("Translation skipped: OpenAI client not initialized.")
        yield segments
        return

    # Process in chunks to provide real-time feedback
    for i in range(0, len(segments), chunk_size):
        chunk = segments[i:i + chunk_size]
        texts = [s['text'] for s in chunk]
        
        system_prompt = f"""You are a professional subtitle translator. 
        Translate the following list of subtitle lines to {target_language}.
        Maintain the tone and context. 
        Return ONLY a JSON array of strings, matching the input array length exactly.
        Do not include any other text or markdown formatting.
        """
        
        user_prompt = json.dumps(texts, ensure_ascii=False)
        
        try:
            content = fetch_translation_with_retry(system_prompt, user_prompt)
            
            # Basic cleaning of the response if it's wrapped in markdown
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
                
            try:
                translated_texts = json.loads(content)
            except json.JSONDecodeError as je:
                print(f"JSON Decode Error for chunk {i}: {je}. Content: {content[:100]}...")
                yield chunk
                continue
            
            # Handle cases where the model returns a wrapper object
            if isinstance(translated_texts, dict):
                found_list = False
                for key, value in translated_texts.items():
                    if isinstance(value, list):
                        translated_texts = value
                        found_list = True
                        break
                if not found_list:
                    print(f"Warning: Could not find translation list in dict for chunk {i}")
                    yield chunk
                    continue
            
            if not isinstance(translated_texts, list):
                print(f"Warning: Expected list but got {type(translated_texts)} for chunk {i}")
                yield chunk
                continue

            if len(translated_texts) != len(chunk):
                print(f"Warning: Mismatch in translation count for chunk {i}. Input: {len(chunk)}, Output: {len(translated_texts)}")
            
            translated_chunk = []
            for j, segment in enumerate(chunk):
                translated_text = translated_texts[j] if j < len(translated_texts) else segment['text']
                translated_chunk.append({
                    "start": segment["start"],
                    "end": segment["end"],
                    "text": translated_text
                })
            
            yield translated_chunk

        except Exception as e:
            print(f"Translation chunk {i} failed after retries: {e}")
            yield chunk # Return original chunk on failure


