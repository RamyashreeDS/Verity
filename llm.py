"""LFM2.5-2.6B running locally: turns free-text reports into road-event JSON."""
import json
import re
import threading
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_PATH = str(Path(__file__).parent / "LFM2.5-2.6B")
DEVICE = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"

_lock = threading.Lock()
_tok = None
_model = None

EXTRACT_PROMPT = """You read reports about San Francisco streets and extract road-status events.
Return ONLY a JSON list. Each item:
{{"blocked": true/false, "street": "main street name, e.g. Market St",
"cross_street": "the single cross street if the report names one intersection, else null",
"from_street": "first bounding street if the report says 'between X and Y', else null",
"to_street": "second bounding street if the report says 'between X and Y', else null",
"reason": "short reason", "type": "parade|protest|strike|market|festival|fire|flood|crash|construction|other",
"hours": estimated hours the closure lasts (number)}}
Use "blocked": false when the report says a road has reopened or cleared.
Return [] if the text does not describe a specific San Francisco street being closed or reopened.
Today is {today}. Skip closures that clearly happened on other dates.

Report:
{text}"""


def load():
    global _tok, _model
    with _lock:
        if _model is None:
            _tok = AutoTokenizer.from_pretrained(MODEL_PATH)
            _model = AutoModelForCausalLM.from_pretrained(MODEL_PATH, dtype=torch.bfloat16).to(DEVICE).eval()


def generate(prompt: str, max_new_tokens: int = 300) -> str:
    load()
    with _lock:
        # The chat template opens a <think> block; closing it right away skips reasoning (~10x faster).
        text = _tok.apply_chat_template([{"role": "user", "content": prompt}], add_generation_prompt=True, tokenize=False)
        ids = _tok(text + "</think>\n", return_tensors="pt", add_special_tokens=False).input_ids.to(DEVICE)
        with torch.no_grad():
            out = _model.generate(ids, max_new_tokens=max_new_tokens, do_sample=False, repetition_penalty=1.05)
        return _tok.decode(out[0, ids.shape[1]:], skip_special_tokens=True)


def extract_events(text: str, today: str) -> tuple[list[dict], str]:
    raw = generate(EXTRACT_PROMPT.format(text=text[:2500], today=today))
    m = re.search(r"\[.*\]|\{.*\}", raw, re.S)
    if not m:
        return [], raw
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return [], raw
    if isinstance(data, dict):
        data = [data]
    events = [d for d in data if isinstance(d, dict) and d.get("street")]
    return events, raw
