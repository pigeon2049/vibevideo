import os
import json
import re
import time
import logging
import asyncio
from typing import List, Dict, Generator, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI
from app.core.config import settings

logger = logging.getLogger("vibe-video.translation")

class TranslationService:
    def __init__(self):
        self.providers = []
        self.strategy = os.getenv("LLM_STRATEGY", settings.LLM_STRATEGY)
        self.current_index = 0
        self._load_providers()

    def _load_providers(self):
        # Load numbered providers from env
        for i in range(11): # 0 (default) to 10
            suffix = str(i) if i > 0 else ""
            api_key = os.environ.get(f"OPENAI_API_KEY{suffix}")
            base_url = os.environ.get(f"OPENAI_API_BASE{suffix}") or os.environ.get(f"OPENAI_BASE_URL{suffix}")
            model = os.environ.get(f"LLM_MODEL{suffix}")
            
            if api_key or base_url or model:
                self.providers.append({
                    "client": OpenAI(
                        api_key=api_key or "ollama",
                        base_url=base_url or "http://localhost:11434/v1"
                    ),
                    "model": model or settings.LLM_MODEL,
                    "name": f"Provider-{i if i > 0 else 'default'}"
                })
                
        if not self.providers:
            logger.warning("No LLM providers configured, using fallback Ollama")
            self.providers.append({
                "client": OpenAI(api_key="ollama", base_url="http://localhost:11434/v1"),
                "model": settings.LLM_MODEL,
                "name": "Fallback"
            })
            
        logger.info(f"Loaded {len(self.providers)} providers. Strategy: {self.strategy}")

    def get_provider(self, attempt=0) -> Dict:
        if self.strategy in ["round_robin", "concurrent"]:
            provider = self.providers[self.current_index % len(self.providers)]
            self.current_index += 1
            return provider
        else: # priority
            return self.providers[attempt % len(self.providers)]

    def _build_prompt(self, target_lang: str, video_title: str, context_text: str, current_segments: List[Dict], video_summary: str = "") -> str:
        segments_json = json.dumps(current_segments, ensure_ascii=False)
        summary_section = f"\nVIDEO CONTEXT/SUMMARY:\n{video_summary}\n" if video_summary else ""
        return f"""You are a professional video subtitle translator. 
Video Title: {video_title}{summary_section}
Target Language: {target_lang}

CONTEXT FOR REFERENCE (PREVIOUSLY TRANSLATED SENTENCES):
{context_text}

TASK: Translate the following subtitle segments into {target_lang}.

STRICT REQUIREMENTS:
1. Maintain the exact same JSON structure.
2. Only translate the "text" field.
3. Return ONLY the JSON list of translated segments.
4. DO NOT REPEAT ANY TEXT FROM THE CONTEXT in your translation.
7. DO NOT add any trailing connectives or "bridge" words at the end of a segment (e.g., "它...", "并在...", "而是...") just to connect to the next segment. Each segment must be a clean translation of its source.
8. The context is only there to help you understand the story, not to be repeated.

Segments to translate:
{segments_json}
"""

    def _build_review_prompt(self, target_lang: str, video_title: str, context_text: str, original_segments: List[Dict], translated_segments: List[Dict], video_summary: str = "") -> str:
        original_json = json.dumps(original_segments, ensure_ascii=False)
        translated_json = json.dumps(translated_segments, ensure_ascii=False)
        summary_section = f"\nVIDEO CONTEXT/SUMMARY:\n{video_summary}\n" if video_summary else ""
        return f"""You are a translation reviewer. Your task is to review and improve the translation of video subtitles.
Video Title: {video_title}{summary_section}
Target Language: {target_lang}

CONTEXT FOR REFERENCE (PREVIOUSLY TRANSLATED SENTENCES):
{context_text}

ORIGINAL SEGMENTS:
{original_json}

INITIAL TRANSLATION:
{translated_json}

GOAL: Review the INITIAL TRANSLATION and improve it. 
Ensure the translation is natural, contextually accurate, and consistent with the video title and previous context.

STRICT REQUIREMENTS:
1. Return ONLY the improved JSON list of translated segments.
2. Maintain the same JSON structure as the input.
3. Only modify the "text" field if it can be improved.
4. DO NOT REPEAT ANY TEXT FROM THE CONTEXT.
5. DO NOT add any trailing connectives, pronouns, or ellipses at the end of segments to link them to the next segment.
6. If the initial translation is already perfect, return it as is but still in the same JSON format.

Improved Translation:
"""

    def _build_coherence_prompt(self, target_lang: str, video_title: str, context_text: str, current_segments: List[Dict], video_summary: str = "") -> str:
        segments_json = json.dumps(current_segments, ensure_ascii=False)
        summary_section = f"\nVIDEO CONTEXT/SUMMARY:\n{video_summary}\n" if video_summary else ""
        
        # Extract the very last bit of context to emphasize the connection
        last_context = context_text[-100:] if len(context_text) > 100 else context_text
        
        return f"""You are a translation coherence expert. Your task is to ensure the translation flows naturally from the previous context.
Video Title: {video_title}{summary_section}
Target Language: {target_lang}

PREVIOUS CONTEXT (ENDING):
...{last_context}

CURRENT TRANSLATED SEGMENTS:
{segments_json}

TASK: Review the first segment of the CURRENT TRANSLATED SEGMENTS and ensure it connects perfectly with the ending of the PREVIOUS CONTEXT. 
If a sentence was previously cut off, ensure it completes naturally. If the tone or subject changed abruptly, fix it.

STRICT REQUIREMENTS:
1. Return ONLY the JSON list of segments.
2. Only modify the "text" field for coherence.
3. DO NOT REPEAT ANY TEXT FROM THE CONTEXT.
4. DO NOT add any bridge words (like "它...", "并在...") at the end of segments. Ensure each segment ends where the source idea ends.
5. If it already flows perfectly, return the input exactly.

Coherent Translation:
"""

    async def translate_segments_stream(
        self, 
        segments: List[Dict], 
        target_language: str, 
        video_title: str = "Unknown Video",
        history_context: List[str] = [], 
        chunk_size: int = 5,
        video_summary: str = ""
    ):
        context_buffer = history_context.copy()
        total_chunks = (len(segments) + chunk_size - 1) // chunk_size
        
        logger.info(f"Starting translation: {len(segments)} segments in {total_chunks} chunks. Strategy: {self.strategy}")

        if self.strategy == "concurrent":
            max_workers = len(self.providers)
            all_chunks = []
            for i in range(0, len(segments), chunk_size):
                chunk = segments[i : i + chunk_size]
                all_chunks.append((i // chunk_size + 1, chunk))

            results_map = {}
            next_expected_idx = 1
            loop = asyncio.get_running_loop()

            async def process_one_chunk(idx, chunk_data):
                nonlocal next_expected_idx
                # Capture current context snapshot for this chunk - use more context
                context_text = " ".join(context_buffer[-15:])
                translated = await self._translate_chunk_with_retry(
                    chunk_data, target_language, video_title, context_text, idx, total_chunks, video_summary=video_summary
                )
                return idx, translated

            # Launch all tasks
            tasks = [process_one_chunk(idx, chunk) for idx, chunk in all_chunks]
            
            for coro in asyncio.as_completed(tasks):
                idx, translated_chunk = await coro
                results_map[idx] = translated_chunk
                
                # Yield in order
                while next_expected_idx in results_map:
                    chunk_res = results_map.pop(next_expected_idx)
                    for seg in chunk_res:
                        # Deduplicate against previous context
                        seg['text'] = self._deduplicate_segment(seg.get('text', ''), context_buffer)
                        context_buffer.append(seg.get('text', ''))
                    yield chunk_res
                    next_expected_idx += 1
        else:
            # Sequential strategy
            for i in range(0, len(segments), chunk_size):
                chunk_idx = i // chunk_size + 1
                chunk = segments[i : i + chunk_size]
                context_text = " ".join(context_buffer[-15:])
                
                translated_chunk = await self._translate_chunk_with_retry(
                    chunk, target_language, video_title, context_text, chunk_idx, total_chunks, video_summary=video_summary
                )
                if translated_chunk:
                    for seg in translated_chunk:
                        # Deduplicate against previous context
                        seg['text'] = self._deduplicate_segment(seg.get('text', ''), context_buffer)
                        context_buffer.append(seg.get('text', ''))
                    yield translated_chunk

    def _deduplicate_segment(self, current_text: str, context_buffer: List[str]) -> str:
        """
        Removes overlapping repetition from the start of current_text if it mirrors 
        the end of the previous translations. Works for both English (words) and 
        Chinese (characters).
        """
        if not context_buffer or not current_text:
            return current_text
            
        prev_text = " ".join(context_buffer[-2:]).strip()
        if not prev_text:
            return current_text
            
        curr = current_text.strip()
        
        # Try to find the longest character-based overlap
        # Check from longest possible overlap down to threshold
        # In Chinese, even 1-2 character overlaps (like pronouns "它", "其") are significant
        has_chinese = any('\u4e00' <= char <= '\u9fff' for char in curr + prev_text)
        min_overlap = 2 if has_chinese else 4
        
        max_overlap_len = min(len(prev_text), len(curr))
        for length in range(max_overlap_len, min_overlap - 1, -1):
            overlap_prev = prev_text[-length:]
            overlap_curr = curr[:length]
            
            if overlap_prev.lower() == overlap_curr.lower():
                logger.info(f"Deduplicating overlap (len {length}): '{overlap_curr}'")
                new_text = curr[length:].strip()
                # Remove leading punctuation
                new_text = re.sub(r'^[，。！？；、,.!?;:\-\s]+', '', new_text).strip()
                return new_text
                
        return current_text

    async def _translate_chunk_with_retry(self, chunk, target_lang, video_title, context_text, idx, total, max_retries=3, video_summary=""):
        attempt = 0
        while attempt < max_retries:
            provider = self.get_provider(attempt=attempt)
            client = provider["client"]
            model = provider["model"]
            
            logger.info(f"Translating chunk {idx}/{total} with {provider['name']} (attempt {attempt+1})")
            
            try:
                loop = asyncio.get_running_loop()
                # 1. Initial Translation
                response = await loop.run_in_executor(None, lambda: client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You are a specialized translator. Output valid JSON array ONLY."},
                        {"role": "user", "content": self._build_prompt(target_lang, video_title, context_text, chunk, video_summary=video_summary)}
                    ],
                    temperature=0.3,
                    timeout=180
                ))
                
                content = response.choices[0].message.content.strip()
                initial_translated_chunk = self._parse_json_response(content)
                
                if not self._validate_translation(chunk, initial_translated_chunk, target_lang, content):
                    logger.warning(f"Initial translation validation failed for chunk {idx}, retry...")
                    attempt += 1
                    continue

                # 2. Content Review and Improvement
                logger.info(f"Reviewing translation for chunk {idx}/{total} with {provider['name']}")
                review_response = await loop.run_in_executor(None, lambda: client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You are a translation reviewer. Output valid JSON array ONLY."},
                        {"role": "user", "content": self._build_review_prompt(target_lang, video_title, context_text, chunk, initial_translated_chunk, video_summary=video_summary)}
                    ],
                    temperature=0.2,
                    timeout=300
                ))
                
                review_content = review_response.choices[0].message.content.strip()
                reviewed_chunk = self._parse_json_response(review_content)
                
                if not self._validate_translation(chunk, reviewed_chunk, target_lang, review_content):
                    logger.warning(f"Review translation validation failed for chunk {idx}, using initial...")
                    reviewed_chunk = initial_translated_chunk

                # 3. Coherence Check (Bridge previous context and current chunk)
                logger.info(f"Checking coherence for chunk {idx}/{total} with {provider['name']}")
                coherence_response = await loop.run_in_executor(None, lambda: client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You are a coherence expert. Output valid JSON array ONLY."},
                        {"role": "user", "content": self._build_coherence_prompt(target_lang, video_title, context_text, reviewed_chunk, video_summary=video_summary)}
                    ],
                    temperature=0.1,
                    timeout=300
                ))
                
                coherence_content = coherence_response.choices[0].message.content.strip()
                final_chunk = self._parse_json_response(coherence_content)
                
                if self._validate_translation(chunk, final_chunk, target_lang, coherence_content):
                    return final_chunk
                
                # If coherence failed, return reviewed
                return reviewed_chunk
                
            except Exception as e:
                logger.error(f"Error in translation chunk {idx}: {e}")
            
            attempt += 1
            await asyncio.sleep(2)
            
        logger.warning(f"Failed to translate chunk {idx} after {max_retries} attempts. Returning original text.")
        return chunk

    def _parse_json_response(self, content: str) -> List[Dict]:
        try:
            # More robust JSON cleaning
            clean_content = re.sub(r'```json\s*|```', '', content).strip()
            # If still starts with something before [, try to find [
            if not clean_content.startswith('['):
                match = re.search(r'\[.*\]', clean_content, re.DOTALL)
                if match:
                    clean_content = match.group(0)

            raw_data = json.loads(clean_content)
            if isinstance(raw_data, list):
                return raw_data
            elif isinstance(raw_data, dict):
                for val in raw_data.values():
                    if isinstance(val, list):
                        return val
        except Exception as e:
            logger.error(f"JSON Parse Error: {e}. Content preview: {content[:100]}...")
        return []

    def _validate_translation(self, original_chunk, translated_chunk, target_lang, raw_content) -> bool:
        if not translated_chunk or len(translated_chunk) != len(original_chunk):
            logger.warning(f"Count mismatch: expected {len(original_chunk)}, got {len(translated_chunk) if translated_chunk else 0}")
            return False
            
        # Parroting check
        parrot_count = sum(1 for og, tr in zip(original_chunk, translated_chunk) if og['text'].strip() == str(tr.get('text', '')).strip())
        if parrot_count == len(original_chunk) and len(original_chunk) > 0:
            logger.warning("LLM parroted the original text.")
            return False
            
        # Language check (Chinese specifically)
        if target_lang in ['Chinese', 'zh', 'zh-CN']:
            has_chinese = any('\u4e00' <= char <= '\u9fff' for char in raw_content)
            if not has_chinese:
                logger.warning("No Chinese characters found in output.")
                return False
                
        return True

    async def summarize_video_description(self, description: str, target_lang: str) -> str:
        if not description or len(description.strip()) < 10:
            return ""
            
        provider = self.get_provider(attempt=0)
        client = provider["client"]
        model = provider["model"]
        
        prompt = f"""Summarize the following video description into a concise paragraph (max 200 words) in {target_lang}.
Focus on:
1. The main topic/theme.
2. Key terminology or specialized names mentioned.
3. The overall tone.

Video Description:
{description}

Summary:"""

        try:
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(None, lambda: client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that summarizes video metadata to provide context for translators."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=500
            ))
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Error summarizing description: {e}")
            return ""

translation_service = TranslationService()

