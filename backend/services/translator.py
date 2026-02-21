import os
import json
import re
import time
from typing import List, Dict, Generator
from openai import OpenAI  # 新版导入方式
from dotenv import load_dotenv

load_dotenv()

# 优先级：.env里的OPENAI_API_BASE > .env里的OPENAI_BASE_URL > 默认官方地址
base_url = os.getenv("OPENAI_API_BASE") or os.getenv("OPENAI_BASE_URL") or "http://localhost:11434/v1"
api_key = os.getenv("OPENAI_API_KEY", "ollama")

print(f"📡 Current LLM Config - URL: {base_url}, Model: {os.getenv('LLM_MODEL')}")

client = OpenAI(
    api_key=api_key,
    base_url=base_url
)

class Translator:
    def __init__(self):
        self.model = os.getenv("LLM_MODEL", "gpt-3.5-turbo")

    def _build_prompt(self, target_lang: str, context_text: str, current_segments: List[Dict]) -> str:
        segments_json = json.dumps(current_segments, ensure_ascii=False)
        return f"""You are a professional video subtitle translator. 
Target Language: {target_lang}

Context for reference (previous translated sentences):
{context_text}

Task: Translate the following subtitle segments into {target_lang}.
Requirements:
1. Maintain the exact same JSON structure.
2. Only translate the "text" field.
3. Return ONLY the JSON list of translated segments.

Segments to translate:
{segments_json}
"""

    def translate_segments_stream(
        self, 
        segments: List[Dict], 
        target_language: str, 
        history_context: List[str] = [], 
        chunk_size: int = 5
    ) -> Generator[List[Dict], None, None]:
        
        context_buffer = history_context.copy()
        total_chunks = (len(segments) + chunk_size - 1) // chunk_size
        
        print(f"🚀 Starting translation: {len(segments)} segments, {total_chunks} chunks.")

        for i in range(0, len(segments), chunk_size):
            chunk_idx = i // chunk_size + 1
            chunk = segments[i : i + chunk_size]
            context_text = " ".join(context_buffer[-8:])
            
            print(f"📡 Sending Chunk {chunk_idx}/{total_chunks} to LLM...")
            
            retry_count = 0
            while True:
                start_time = time.time()
                try:
                    # 新版 OpenAI 语法
                    response = client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": "You are a specialized translator. Output valid JSON array ONLY."},
                            {"role": "user", "content": self._build_prompt(target_language, context_text, chunk)}
                        ],
                        temperature=0.3,
                        timeout=180  # 修改为 3 分钟 (180秒)
                    )

                    duration = time.time() - start_time
                    content = response.choices[0].message.content.strip()
                    print(f"✅ Received Chunk {chunk_idx} from LLM ({duration:.2f}s)")

                    # 健壮的 JSON 提取逻辑
                    translated_chunk = []
                    try:
                        clean_content = re.sub(r'```json\s*|```', '', content).strip()
                        raw_data = json.loads(clean_content)
                        if isinstance(raw_data, list):
                            translated_chunk = raw_data
                        elif isinstance(raw_data, dict):
                            for val in raw_data.values():
                                if isinstance(val, list):
                                    translated_chunk = val
                                    break
                    except Exception as json_err:
                        print(f"⚠️ JSON Parse Error: {json_err}. Retrying...")
                        time.sleep(2)
                        continue

                    if not translated_chunk or len(translated_chunk) != len(chunk):
                        expected = len(chunk)
                        actual = len(translated_chunk) if translated_chunk else 0
                        print(f"⚠️ Count mismatch! Expected {expected}, got {actual}. Retrying...")
                        time.sleep(2)
                        continue

                    # 防复读机逻辑：如果所有句子的翻译和原句完全一样，说明模型偷懒了
                    parrot_count = sum(1 for og, tr in zip(chunk, translated_chunk) if og['text'].strip() == str(tr.get('text', '')).strip())
                    if parrot_count == len(chunk) and len(chunk) > 0:
                        print(f"⚠️ LLM parroted the original text without translation. Retrying...")
                        time.sleep(2)
                        continue

                    # 防胡言乱语逻辑：如果目标是中文，结果必须包含中文字符
                    if target_language in ['Chinese', 'zh']:
                        has_chinese = any('\u4e00' <= char <= '\u9fff' for char in content)
                        if not has_chinese:
                            print(f"⚠️ No Chinese characters found in output. Retrying...")
                            time.sleep(2)
                            continue

                    for seg in translated_chunk:
                        context_buffer.append(seg.get('text', ''))

                    yield translated_chunk
                    break # 成功则退出重试循环

                except Exception as e:
                    retry_count += 1
                    print(f"❌ Connection/LLM Error at chunk {chunk_idx}: {str(e)}. Retrying... (Attempt {retry_count})")
                    time.sleep(3) 

        print("🏁 Translation stream finished.")

_translator = Translator()

# 这里确保参数名与 main.py 的调用匹配
def translate_segments_stream(segments: List[Dict], target_language: str, history_context: List[str] = []):
    return _translator.translate_segments_stream(
        segments=segments, 
        target_language=target_language, 
        history_context=history_context
    )