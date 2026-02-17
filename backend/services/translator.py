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
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=2, min=5, max=20),
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
        timeout=300.0 # 300 seconds timeout for large chunks and slow models
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

def _translate_batch(chunk, target_language, attempt_limit=20):
    """
    Translates a small batch of segments with indexing and validation.
    """
    texts_with_ids = [{"id": i, "text": s['text']} for i, s in enumerate(chunk)]
    
    system_prompt = f"""You are a professional subtitle translator. 
    Translate the following JSON array of subtitle lines to {target_language}.
    Maintain the tone and context.
    
    You MUST return a JSON array of objects with the same IDs and the translated text.
    Format: [{{"id": 0, "trans": "translated text 0"}}, {{"id": 1, "trans": "translated text 1"}}, ...]
    
    Rules:
    1. Respond ONLY with the JSON array.
    2. Ensure EVERY ID from the input is present in the output.
    3. The length of the output array MUST exactly match the input array length ({len(chunk)}).
    """
    
    user_prompt = json.dumps(texts_with_ids, ensure_ascii=False)
    
    for attempt in range(attempt_limit):
        try:
            content = fetch_translation_with_retry(system_prompt, user_prompt)
            
            # Basic cleaning
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            # Parse JSON
            try:
                translated_data = json.loads(content)
            except json.JSONDecodeError as je:
                print(f"JSON Decode Error (Attempt {attempt + 1}/{attempt_limit}): {je}. Retrying...")
                continue
            
            # Handle list/dict wrapping
            if isinstance(translated_data, dict):
                for val in translated_data.values():
                    if isinstance(val, list):
                        translated_data = val
                        break
            
            if not isinstance(translated_data, list):
                print(f"Validation Error: Expected list, got {type(translated_data)} (Attempt {attempt + 1}). Retrying...")
                continue

            # Check for IDs and length
            if len(translated_data) != len(chunk):
                print(f"Validation Error: Count mismatch. Input: {len(chunk)}, Output: {len(translated_data)} (Attempt {attempt + 1}). Retrying...")
                continue
            
            # Create a map for easy lookup and verify IDs
            trans_map = {}
            valid = True
            for item in translated_data:
                if not isinstance(item, dict) or "id" not in item or "trans" not in item:
                    valid = False
                    break
                # Rigorous check: trans should not be empty or whitespace only
                trans_text = item.get("trans", "")
                if not isinstance(trans_text, str) or not trans_text.strip():
                    print(f"Validation Error: Empty translation found for ID {item.get('id')} (Attempt {attempt + 1}). Retrying...")
                    valid = False
                    break
                trans_map[item["id"]] = trans_text
            
            if not valid:
                print(f"Validation Error: Item format invalid (Attempt {attempt + 1}). Retrying...")
                continue
                
            # Verify all indices exist
            results = []
            for i in range(len(chunk)):
                if i not in trans_map:
                    valid = False
                    break
                results.append({
                    "start": chunk[i]["start"],
                    "end": chunk[i]["end"],
                    "text": trans_map[i]
                })
            
            if not valid:
                print(f"Validation Error: Missing IDs in response (Attempt {attempt + 1}). Retrying...")
                continue
                
            return results # Success!

        except Exception as e:
            print(f"Translation batch call failed (Attempt {attempt + 1}): {e}")
            
    return None # Failed all attempts

def _translate_recursive(segments, target_language):
    """
    Tries to translate segments. If fails, splits into smaller chunks.
    20 -> 5 -> 1 -> Fallback
    """
    if not segments:
        return []

    # Attempt current batch
    translated = _translate_batch(segments, target_language)
    if translated:
        return translated
    
    # If failed and can be split
    if len(segments) > 5:
        print(f"Chunk of {len(segments)} failed. Splitting into chunks of 5...")
        new_results = []
        for i in range(0, len(segments), 5):
            sub_chunk = segments[i:i + 5]
            new_results.extend(_translate_recursive(sub_chunk, target_language))
        return new_results
    
    if len(segments) > 1:
        print(f"Chunk of {len(segments)} failed. Splitting into individual lines...")
        new_results = []
        for segment in segments:
            new_results.extend(_translate_recursive([segment], target_language))
        return new_results
    
    # Final fallback for single line
    print(f"Warning: Failed to translate single line after all retries. Falling back to original.")
    return [{
        "start": segments[0]["start"],
        "end": segments[0]["end"],
        "text": segments[0]["text"]
    }]

def translate_segments_stream(segments, target_language="English", chunk_size=5):
    """
    Translates a list of segments to target language in chunks.
    Yields translated chunks one by one.
    """
    if not client:
        print("Translation skipped: OpenAI client not initialized.")
        yield segments
        return

    for i in range(0, len(segments), chunk_size):
        chunk = segments[i:i + chunk_size]
        translated_chunk = _translate_recursive(chunk, target_language)
        yield translated_chunk
