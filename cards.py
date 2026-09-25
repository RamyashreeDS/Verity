"""FLUX (Black Forest Labs) alert cards: a text-to-image illustration plus a Pillow text overlay with the facts."""
import os
import time
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

BFL_URL = "https://api.bfl.ai/v1/flux-pro-1.1"
CARDS = Path(__file__).parent / "data" / "cards"
CARDS.mkdir(parents=True, exist_ok=True)

SCENE = {
    "protest": "a crowd of people holding blank signs marching down the street",
    "parade": "a colorful parade with floats and balloons filling the street",
    "market": "a farmers market with striped canopy stalls and produce crates along the street",
    "festival": "a street festival with string lights, a small stage and food stalls",
    "fire": "fire trucks with ladders and hoses in front of a building, smoke in the sky",
    "flood": "water covering the street with sandbags at the curb",
    "crash": "tow trucks and traffic cones around a blocked intersection",
    "construction": "an excavator, orange cones and a construction crew digging up the street",
    "strike": "workers with blank picket signs standing across the street",
    "special event": "a lively block party with tables, bunting and people in the street",
    "roadway shared spaces": "outdoor cafe tables and planters occupying a car-free street",
    "special traffic permit": "utility trucks, orange cones and a work crew on the street",
}
STYLE = ("flat vector poster illustration, bold minimal shapes, warm orange and red palette, "
         "San Francisco street with Victorian houses and hills in the background, "
         "a red and white road-closed barrier in the foreground, no text, no letters, no words")


def _font(size: int, bold: bool = True):
    for p in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def flux_image(prompt: str, width: int = 1024, height: int = 768) -> Image.Image:
    key = os.environ.get("BLACK_FORTRESS_API_KEY") or os.environ.get("BFL_API_KEY")
    if not key:
        raise RuntimeError("BLACK_FORTRESS_API_KEY not set")
    headers = {"x-key": key, "Content-Type": "application/json"}
    req = requests.post(BFL_URL, headers=headers, timeout=30,
                        json={"prompt": prompt, "width": width, "height": height, "safety_tolerance": 2}).json()
    poll = req["polling_url"]
    for _ in range(60):
        res = requests.get(poll, headers=headers, timeout=20).json()
        if res.get("status") == "Ready":
            img = requests.get(res["result"]["sample"], timeout=60)
            path = CARDS / "_raw.jpg"
            path.write_bytes(img.content)
            return Image.open(path).convert("RGB")
        if res.get("status") not in ("Pending", "Request Moderated", "Task not found"):
            raise RuntimeError(f"FLUX status {res.get('status')}")
        time.sleep(1)
    raise RuntimeError("FLUX timed out")


def make_card(ev: dict) -> str:
    """Returns the URL path of the generated card. Cached per event id."""
    out = CARDS / f"{ev['id']}.jpg"
    if out.exists():
        return f"/cards/{out.name}"

    scene = SCENE.get((ev.get("type") or "other").lower(), "orange cones and a police car blocking the street")
    img = flux_image(f"{STYLE}, {scene}")
    W, H = img.size
    draw = ImageDraw.Draw(img, "RGBA")

    # Bottom band with the facts
    band_h = 210
    draw.rectangle([0, H - band_h, W, H], fill=(15, 17, 21, 225))
    draw.rectangle([0, H - band_h, W, H - band_h + 8], fill=(220, 38, 38, 255))
    headline = "ROAD CLOSED" if ev["status"] == "blocked" else "LANES CLOSED"
    draw.text((36, H - band_h + 28), headline, font=_font(54), fill=(239, 68, 68))
    street = (ev["streets"][0] if ev["streets"] else "").upper()
    if len(street) > 44:
        street = street[:42] + "…"
    draw.text((36, H - band_h + 96), street, font=_font(34), fill=(255, 255, 255))
    until = ev["ends_at"][5:16].replace("T", " ")
    kinds = sorted({s.get("kind", "") for s in ev.get("sources", [])})
    detail = f"{ev['title'][:50]}  ·  until {until}  ·  confidence {ev['confidence']:.2f}  ·  sources: {', '.join(kinds)}"
    draw.text((36, H - band_h + 150), detail, font=_font(21, bold=False), fill=(200, 208, 224))

    # Top-left tag: never let this pass as a photo
    tag = "AI ILLUSTRATION · RoadWatch SF · FLUX by Black Forest Labs"
    f = _font(18, bold=False)
    tw = draw.textlength(tag, font=f)
    draw.rectangle([16, 16, 16 + tw + 24, 52], fill=(15, 17, 21, 200))
    draw.text((28, 24), tag, font=f, fill=(251, 191, 36))

    img.save(out, quality=88)
    return f"/cards/{out.name}"
