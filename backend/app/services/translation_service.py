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

    def _build_coherence_prompt(self, target_lang: str, video_title: str, context_segments: List[Dict], current_segments: List[Dict], video_summary: str = "") -> str:
        current_json = json.dumps(current_segments, ensure_ascii=False)
        context_json = json.dumps(context_segments[-3:], ensure_ascii=False) if context_segments else "[]"
        summary_section = f"\nVIDEO CONTEXT/SUMMARY:\n{video_summary}\n" if video_summary else ""
        
        return f"""You are a translation coherence expert. Your task is to ensure the translation flows naturally and correct any fundamental errors in previous segments based on new information.
Video Title: {video_title}{summary_section}
Target Language: {target_lang}

RECENT CONTEXT (LAST 3 TRANSLATED SEGMENTS):
{context_json}

CURRENT TRANSLATED CHUNK (JUST COMPLETED):
{current_json}

TASK: 
1. Review the CURRENT TRANSLATED CHUNK to ensure it connects perfectly with the RECENT CONTEXT.
2. If you find a fundamental issue in a segment from the RECENT CONTEXT (e.g., a person's name was wrong, a sentence was cut off poorly, or the tone is inconsistent), you MUST suggest a correction for that previous segment.
3. Each segment must be a clean translation. Do not add bridge words (like "它...", "并在...") at the end of segments.

STRICT REQUIREMENTS:
1. Return a JSON object with two fields:
   "current_chunk": The (possibly improved) list of segments from the CURRENT TRANSLATED CHUNK.
   "corrections": A list of segments from the RECENT CONTEXT that need updating. If none, return an empty list [].
2. Maintain the exact same JSON structure for segments.
3. Only modify the "text" field.
4. DO NOT REPEAT ANY TEXT FROM THE CONTEXT in the "current_chunk" translations.
5. If everything is perfect, return the input segments in "current_chunk" and [] in "corrections".

Example Output:
{{
  "current_chunk": [{{ "id": "seg4", "text": "..." }}, ...],
  "corrections": [{{ "id": "seg3", "text": "Corrected text for seg3" }}]
}}

Coherent Review:
"""

    def _clean_speaker_label(self, text: str) -> str:
        if not text:
            return text
        import re
        pattern = r'^(?:\[[^\]]{1,30}\]|\([^)]{1,30}\)|[A-Z][A-Za-z0-9-]*\s?(?:[A-Z0-9][A-Za-z0-9-]*\s?){0,2}|[\u4e00-\u9fa5]{2,5})[:：]\s*'
        return re.sub(pattern, '', text).strip()

    def _postprocess_translation(self, text: str) -> str:
        if not text:
            return text
        # Remove markdown quotes or translation: prefixes
        if text.startswith('“') and text.endswith('”'):
            text = text[1:-1]
        elif text.startswith('"') and text.endswith('"'):
            text = text[1:-1]
            
        if '翻译：' in text or '翻译:"' in text or '翻译：“' in text:
            text = re.sub(r'^.*?翻译[：:]\s*["“]?(.*?)["”]?\s*$', r'\1', text, flags=re.DOTALL)
            
        text = text.replace('...', '，').replace('…', '，')
        text = text.replace('————', '：').replace('——', '：')
        return text.strip()

    def _build_overall_review_prompt(self, target_lang: str, video_title: str, segments: List[Dict], video_summary: str = "") -> str:
        segments_json = json.dumps(segments, ensure_ascii=False)
        summary_section = f"\nVIDEO CONTEXT/SUMMARY:\n{video_summary}\n" if video_summary else ""
        return f"""You are a professional video subtitle editor. 
Video Title: {video_title}{summary_section}
Target Language: {target_lang}

TASK: Perform a final coherency pass on this block of sequentially translated subtitle segments.
These segments were translated independently. Your goals are:
1. CONDENSE wordy or overly literal translations.
2. REMOVE redundant words or repeated meanings that exist because a sentence was split across two segments. If a meaning is fully expressed in segment 1, remove the trailing half-sentence from segment 2, or vice versa, to make both segments sound natural on their own.
3. FIX unnatural phrasing.

STRICT REQUIREMENTS:
1. Maintain the exact same JSON structure. Every ID must remain exactly as it is.
2. Only modify the "text" field.
3. Return ONLY the JSON list of updated segments. DO NOT merge segments. Return the exact same number of segments.
4. If a segment is already perfect and requires no change, return it exactly as it is.

Segments block:
{segments_json}

Improved Translation:
"""

    def _build_transcription_correction_prompt(self, video_title: str, segments: List[Dict], video_description: str = "") -> str:
        segments_json = json.dumps(segments, ensure_ascii=False)
        description_section = f"\nVIDEO DESCRIPTION:\n{video_description}\n" if video_description else ""
        return f"""You are a professional subtitle transcript editor. 
Video Title: {video_title}{description_section}

TASK: Review the following transcribed subtitle segments and correct any speech recognition errors (like homophones or misspelled names) using the video context. 
ALSO, you MUST completely remove any speaker labels (e.g., "John:", "[Speaker 1]:", "(Male voice)") from the text.

STRICT REQUIREMENTS:
1. Maintain the exact same JSON structure. Every ID must remain exactly as it is.
2. Only modify the "text" field to correct errors and remove speaker labels. Keep the original language (do NOT translate).
3. Return ONLY the JSON list of updated segments. DO NOT merge segments. Return the exact same number of segments.
4. If a segment is perfectly correct and has no speaker labels, return it exactly as it is.

Segments to correct:
{segments_json}

Corrected Transcripts:
"""

    def _adjust_segment_timing(self, current_seg: Dict, next_seg: Optional[Dict], target_lang: str):
        """
        Extends the 'end' time of current_seg if the text is too long for its duration,
        provided there is empty space before the next segment.
        """
        if not current_seg or 'text' not in current_seg:
            return

        text = current_seg['text']
        start = current_seg['start']
        end = current_seg['end']
        duration = end - start

        if duration <= 0:
            return

        # Simple heuristic for reading speed limits (characters/words per second)
        is_chinese = any('\u4e00' <= c <= '\u9fff' for c in text)
        limit_cps = 5.0 if is_chinese else 15.0 # chars per sec for zh, approx "chars" (inc spaces) for en
        
        actual_cps = len(text) / duration

        # If it's too fast, we want to extend the end time, up to the next segment's start time
        if actual_cps > limit_cps:
            desired_duration = len(text) / limit_cps
            ideal_end = start + desired_duration

            # Determine the maximum allowed end time
            max_end = next_seg['start'] if next_seg else ideal_end + 5.0 # buffer for the last segment

            # Expand end time, but leave a small 0.1s gap if it hits the next segment
            new_end = min(ideal_end, max_end - 0.1)
            
            if new_end > end:
                logger.info(f"Adjusting timing for {current_seg['id']}: {end:.2f} -> {new_end:.2f} (Speed: {actual_cps:.1f} cps)")
                current_seg['end'] = round(new_end, 3)

    async def overall_translate_review_stream(
        self,
        segments: List[Dict],
        target_language: str,
        video_title: str = "Unknown Video",
        video_summary: str = "",
        chunk_size: int = 30
    ):
        """
        A final review pass over the translated segments.
        Processes in larger chunks, fixes redundancies, and adjusts timings.
        """
        total_chunks = (len(segments) + chunk_size - 1) // chunk_size
        logger.info(f"Starting Final Overall Review: {len(segments)} segments in {total_chunks} chunks.")

        for i in range(0, len(segments), chunk_size):
            chunk_idx = i // chunk_size + 1
            chunk = segments[i : i + chunk_size]
            next_seg_start = segments[i + chunk_size]['start'] if i + chunk_size < len(segments) else None
            
            # Use original translation if review fails
            final_chunk = chunk 
            
            # Send to LLM for review
            attempt = 0
            while attempt < 3:
                provider = self.get_provider(attempt=attempt)
                client = provider["client"]
                model = provider["model"]
                
                logger.info(f"Final Review chunk {chunk_idx}/{total_chunks} with {provider['name']} (attempt {attempt+1})")
                try:
                    loop = asyncio.get_running_loop()
                    response = await loop.run_in_executor(None, lambda: client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": "You are a professional subtitle editor. Output valid JSON array ONLY."},
                            {"role": "user", "content": self._build_overall_review_prompt(target_language, video_title, chunk, video_summary=video_summary)}
                        ],
                        temperature=0.2,
                        timeout=300
                    ))
                    
                    content = response.choices[0].message.content.strip()
                    reviewed_chunk = self._parse_json_response(content)
                    
                    if self._validate_translation(chunk, reviewed_chunk, target_language, content):
                        final_chunk = reviewed_chunk
                        break
                    else:
                        logger.warning(f"Final review validation failed for chunk {chunk_idx}, retry...")
                except Exception as e:
                    logger.error(f"Error in final review chunk {chunk_idx}: {e}")
                
                attempt += 1
                await asyncio.sleep(2)
            
            # Adjust timings for each segment in the chunk
            for j, seg in enumerate(final_chunk):
                # We need the next segment to determine the gap
                next_seg_in_chunk = final_chunk[j+1] if j + 1 < len(final_chunk) else None
                # If it's the last segment in the chunk, use the first segment of the next chunk
                if not next_seg_in_chunk and next_seg_start is not None:
                    next_seg_in_chunk = {'start': next_seg_start}
                
                if 'text' in seg:
                    seg['text'] = self._postprocess_translation(seg.get('text', ''))
                self._adjust_segment_timing(seg, next_seg_in_chunk, target_language)
            
            yield final_chunk

    async def correct_transcription_segments(
        self,
        segments: List[Dict],
        video_title: str = "Unknown Video",
        video_description: str = "",
        chunk_size: int = 30
    ) -> List[Dict]:
        """
        A synchronous correction pass over the transcribed segments to fix words and remove speaker labels.
        """
        total_chunks = (len(segments) + chunk_size - 1) // chunk_size
        logger.info(f"Starting Transcription Correction: {len(segments)} segments in {total_chunks} chunks.")
        
        corrected_segments = []

        for i in range(0, len(segments), chunk_size):
            chunk_idx = i // chunk_size + 1
            chunk = segments[i : i + chunk_size]
            
            final_chunk = chunk 
            
            attempt = 0
            while attempt < 3:
                provider = self.get_provider(attempt=attempt)
                client = provider["client"]
                model = provider["model"]
                
                logger.info(f"Correction chunk {chunk_idx}/{total_chunks} with {provider['name']} (attempt {attempt+1})")
                try:
                    loop = asyncio.get_running_loop()
                    prompt = self._build_transcription_correction_prompt(video_title, chunk, video_description=video_description)
                    response = await loop.run_in_executor(None, lambda: client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": "You are a professional transcript editor. Output valid JSON array ONLY."},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.2,
                        timeout=300
                    ))
                    
                    content = response.choices[0].message.content.strip()
                    reviewed_chunk = self._parse_json_response(content)
                    
                    if len(reviewed_chunk) == len(chunk):
                        # Clean labels as a fallback
                        for seg in reviewed_chunk:
                            if 'text' in seg:
                                seg['text'] = self._clean_speaker_label(seg['text'])
                        final_chunk = reviewed_chunk
                        break
                    else:
                        logger.warning(f"Correction validation failed for chunk {chunk_idx}: size mismatch, retry...")
                except Exception as e:
                    logger.error(f"Error in correction chunk {chunk_idx}: {e}")
                
                attempt += 1
                await asyncio.sleep(2)
            
            corrected_segments.extend(final_chunk)
            
        return corrected_segments

    async def translate_segments_stream(
        self, 
        segments: List[Dict], 
        target_language: str, 
        video_title: str = "Unknown Video",
        history_segments: List[Dict] = [], 
        chunk_size: int = 5,
        video_summary: str = ""
    ):
        for seg in segments:
            if 'text' in seg:
                seg['text'] = self._clean_speaker_label(seg['text'])
        for seg in history_segments:
            if 'text' in seg:
                seg['text'] = self._clean_speaker_label(seg['text'])

        context_segments = history_segments.copy()
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
                # Pass segments for context
                translated_result = await self._translate_chunk_with_retry(
                    chunk_data, target_language, video_title, context_segments, idx, total_chunks, video_summary=video_summary
                )
                return idx, translated_result

            # Launch all tasks
            tasks = [process_one_chunk(idx, chunk) for idx, chunk in all_chunks]
            
            for coro in asyncio.as_completed(tasks):
                idx, translated_chunk = await coro
                results_map[idx] = translated_chunk
                
                # Yield in order
                while next_expected_idx in results_map:
                    result = results_map.pop(next_expected_idx)
                    chunk_res = result["chunk"]
                    corrections = result["corrections"]
                    
                    # Yield corrections first
                    if corrections:
                        yield corrections

                    for seg in chunk_res:
                        # Deduplicate against previous context
                        context_texts = [s.get('text', '') for s in context_segments[-15:]]
                        seg['text'] = self._deduplicate_segment(seg.get('text', ''), context_texts)
                        seg['text'] = self._postprocess_translation(seg.get('text', ''))
                        context_segments.append(seg)
                    yield chunk_res
                    next_expected_idx += 1
        else:
            # Sequential strategy
            for i in range(0, len(segments), chunk_size):
                chunk_idx = i // chunk_size + 1
                chunk = segments[i : i + chunk_size]
                
                result = await self._translate_chunk_with_retry(
                    chunk, target_language, video_title, context_segments, chunk_idx, total_chunks, video_summary=video_summary
                )
                if result:
                    chunk_res = result["chunk"]
                    corrections = result["corrections"]
                    
                    if corrections:
                        yield corrections
                        
                    for seg in chunk_res:
                        context_texts = [s.get('text', '') for s in context_segments[-15:]]
                        seg['text'] = self._deduplicate_segment(seg.get('text', ''), context_texts)
                        seg['text'] = self._postprocess_translation(seg.get('text', ''))
                        context_segments.append(seg)
                    yield chunk_res

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

    async def _translate_chunk_with_retry(self, chunk, target_lang, video_title, context_segments, idx, total, max_retries=3, video_summary=""):
        attempt = 0
        context_text = " ".join([s.get('text', '') for s in context_segments[-15:]])
        
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

                # 3. Coherence Check (Bridge previous context and current chunk + Back-correction)
                logger.info(f"Checking coherence and back-corrections for chunk {idx}/{total} with {provider['name']}")
                coherence_response = await loop.run_in_executor(None, lambda: client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You are a coherence expert. Output valid JSON object with 'current_chunk' and 'corrections' fields."},
                        {"role": "user", "content": self._build_coherence_prompt(target_lang, video_title, context_segments, reviewed_chunk, video_summary=video_summary)}
                    ],
                    temperature=0.1,
                    timeout=300
                ))
                
                coherence_content = coherence_response.choices[0].message.content.strip()
                coherence_result = self._parse_json_dict(coherence_content)
                
                final_chunk = coherence_result.get("current_chunk", reviewed_chunk)
                corrections = coherence_result.get("corrections", [])

                if self._validate_translation(chunk, final_chunk, target_lang, coherence_content):
                    return {"chunk": final_chunk, "corrections": corrections}
                
                # If coherence failed validation, return reviewed with no corrections
                return {"chunk": reviewed_chunk, "corrections": []}
                
            except Exception as e:
                logger.error(f"Error in translation chunk {idx}: {e}")
            
            attempt += 1
            await asyncio.sleep(2)
            
        logger.warning(f"Failed to translate chunk {idx} after {max_retries} attempts. Returning original text.")
        return chunk

    def _parse_json_dict(self, content: str) -> Dict:
        try:
            clean_content = re.sub(r'```json\s*|```', '', content).strip()
            if not clean_content.startswith('{'):
                match = re.search(r'\{.*\}', clean_content, re.DOTALL)
                if match:
                    clean_content = match.group(0)

            raw_data = json.loads(clean_content)
            if isinstance(raw_data, dict):
                return raw_data
        except Exception as e:
            logger.error(f"JSON Parse Error (Dict): {e}. Content preview: {content[:100]}...")
        return {"current_chunk": [], "corrections": []}

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

