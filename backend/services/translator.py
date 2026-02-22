import os
import json
import re
import time
from typing import List, Dict, Generator, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI  # 新版导入方式
from dotenv import load_dotenv

load_dotenv()

class Translator:
    def __init__(self):
        self.providers = []
        self.strategy = os.getenv("LLM_STRATEGY", "priority") # 'priority', 'round_robin', or 'concurrent'
        self.current_index = 0
        self._load_providers()

    def _load_providers(self):
        # Load default
        default_api_key = os.getenv("OPENAI_API_KEY")
        default_base_url = os.getenv("OPENAI_API_BASE") or os.getenv("OPENAI_BASE_URL")
        default_model = os.getenv("LLM_MODEL")
        
        if default_api_key or default_base_url or default_model:
            self.providers.append({
                "client": OpenAI(
                    api_key=default_api_key or "ollama", 
                    base_url=default_base_url or "http://localhost:11434/v1"
                ),
                "model": default_model or "gpt-3.5-turbo",
                "name": "Provider-default"
            })
            
        # Load numbered providers based on user request (e.g. 1 to 10)
        for i in range(1, 11):
            api_key = os.getenv(f"OPENAI_API_KEY{i}")
            base_url = os.getenv(f"OPENAI_API_BASE{i}") or os.getenv(f"OPENAI_BASE_URL{i}")
            model = os.getenv(f"LLM_MODEL{i}")
            
            if api_key or base_url or model:
                self.providers.append({
                    "client": OpenAI(
                        api_key=api_key or "ollama",
                        base_url=base_url or "http://localhost:11434/v1"
                    ),
                    "model": model or "gpt-3.5-turbo",
                    "name": f"Provider-{i}"
                })
                
        if not self.providers:
            self.providers.append({
                "client": OpenAI(api_key="ollama", base_url="http://localhost:11434/v1"),
                "model": "gpt-3.5-turbo",
                "name": "Fallback"
            })
            
        provider_names = [p["name"] for p in self.providers]
        print(f"Loaded {len(self.providers)} LLM providers: {', '.join(provider_names)}. Strategy: {self.strategy}")

    def get_provider(self, attempt=0):
        if self.strategy == "round_robin" or self.strategy == "concurrent":
            provider = self.providers[self.current_index % len(self.providers)]
            self.current_index += 1
            return provider
        else: # priority
            return self.providers[attempt % len(self.providers)]

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
        
        print(f"Starting translation: {len(segments)} segments, {total_chunks} chunks.")

        if self.strategy == "concurrent":
            # 并发策略：使用线程池
            max_workers = len(self.providers)
            print(f"Concurrent mode enabled with {max_workers} workers.")
            
            # 准备所有 chunks
            all_chunks = []
            for i in range(0, len(segments), chunk_size):
                chunk = segments[i : i + chunk_size]
                chunk_idx = i // chunk_size + 1
                all_chunks.append((chunk_idx, chunk))
            
            total_chunks = len(all_chunks)
            
            def process_chunk(chunk_info):
                idx, chunk_data = chunk_info
                # 注意：并发模式下，每个 chunk 使用当前的 context_buffer 快照
                # 虽然不能实时获取前一个并发 chunk 的结果，但对于翻译来说通常足够了
                context_text = " ".join(context_buffer[-8:])
                
                attempt_count = 0
                while True:
                    # 分配提供商：轮询
                    provider_idx = (idx - 1) % len(self.providers)
                    provider = self.providers[provider_idx]
                    current_client = provider["client"]
                    current_model = provider["model"]
                    
                    print(f"[Concurrent] Sending Chunk {idx}/{total_chunks} to {provider['name']}...")
                    attempt_count += 1
                    
                    try:
                        response = current_client.chat.completions.create(
                            model=current_model,
                            messages=[
                                {"role": "system", "content": "You are a specialized translator. Output valid JSON array ONLY."},
                                {"role": "user", "content": self._build_prompt(target_language, context_text, chunk_data)}
                            ],
                            temperature=0.3,
                            timeout=180
                        )
                        content = response.choices[0].message.content.strip()
                        
                        # 解析逻辑
                        clean_content = re.sub(r'```json\s*|```', '', content).strip()
                        raw_data = json.loads(clean_content)
                        translated_chunk = []
                        if isinstance(raw_data, list):
                            translated_chunk = raw_data
                        elif isinstance(raw_data, dict):
                            for val in raw_data.values():
                                if isinstance(val, list):
                                    translated_chunk = val
                                    break
                                    
                        if translated_chunk and len(translated_chunk) == len(chunk_data):
                            return idx, translated_chunk
                            
                    except Exception as e:
                        print(f"[Concurrent] Error in chunk {idx}: {str(e)}. Retrying...")
                        if attempt_count > 3:
                            return idx, chunk_data # 失败太多次则返回原句
                        time.sleep(2)

            # 使用 ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交任务
                future_to_chunk = {executor.submit(process_chunk, chunk_info): chunk_info for chunk_info in all_chunks}
                
                next_expected_idx = 1
                results_map = {}
                
                # 按完成顺序获取结果，但按索引顺序 yield
                for future in as_completed(future_to_chunk):
                    idx, translated_chunk = future.result()
                    results_map[idx] = translated_chunk
                    
                    # 检查是否有连续完成的 chunks 可以 yield
                    while next_expected_idx in results_map:
                        chunk_res = results_map.pop(next_expected_idx)
                        print(f"[Concurrent] Ready to yield Chunk {next_expected_idx}")
                        for seg in chunk_res:
                            context_buffer.append(seg.get('text', ''))
                        yield chunk_res
                        next_expected_idx += 1

        else:
            # 顺序策略 (priority 或 round_robin)
            for i in range(0, len(segments), chunk_size):
                chunk_idx = i // chunk_size + 1
                chunk = segments[i : i + chunk_size]
                context_text = " ".join(context_buffer[-8:])
                
                attempt_count = 0
                while True:
                    provider = self.get_provider(attempt=attempt_count)
                    current_client = provider["client"]
                    current_model = provider["model"]
                    
                    print(f"Sending Chunk {chunk_idx}/{total_chunks} to {provider['name']} (Model: {current_model}, Attempt: {attempt_count + 1})...")
                    attempt_count += 1
                    
                    start_time = time.time()
                    try:
                        # 新版 OpenAI 语法
                        response = current_client.chat.completions.create(
                            model=current_model,
                            messages=[
                                {"role": "system", "content": "You are a specialized translator. Output valid JSON array ONLY."},
                                {"role": "user", "content": self._build_prompt(target_language, context_text, chunk)}
                            ],
                            temperature=0.3,
                            timeout=180  # 修改为 3 分钟 (180秒)
                        )

                        duration = time.time() - start_time
                        content = response.choices[0].message.content.strip()
                        print(f"Received Chunk {chunk_idx} from LLM ({duration:.2f}s)")

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
                            print(f"JSON Parse Error: {json_err}. Retrying...")
                            time.sleep(2)
                            continue

                        if not translated_chunk or len(translated_chunk) != len(chunk):
                            expected = len(chunk)
                            actual = len(translated_chunk) if translated_chunk else 0
                            print(f"Count mismatch! Expected {expected}, got {actual}. Retrying...")
                            time.sleep(2)
                            continue

                        # 防复读机逻辑
                        parrot_count = sum(1 for og, tr in zip(chunk, translated_chunk) if og['text'].strip() == str(tr.get('text', '')).strip())
                        if parrot_count == len(chunk) and len(chunk) > 0:
                            print(f"LLM parroted the original text without translation. Retrying...")
                            time.sleep(2)
                            continue

                        # 防胡言乱语逻辑
                        if target_language in ['Chinese', 'zh']:
                            has_chinese = any('\u4e00' <= char <= '\u9fff' for char in content)
                            if not has_chinese:
                                print(f"No Chinese characters found in output. Retrying...")
                                time.sleep(2)
                                continue

                        for seg in translated_chunk:
                            context_buffer.append(seg.get('text', ''))

                        yield translated_chunk
                        break # 成功则退出重试循环

                    except Exception as e:
                        print(f"Connection/LLM Error at chunk {chunk_idx}: {str(e)}. Retrying... (Attempt {attempt_count})")
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