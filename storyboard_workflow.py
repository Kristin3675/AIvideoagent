"""
Storyboard-to-Video Workflow
=============================
Step 1: Claude API  → Break story idea into N scenes (storyboard)
Step 2: SeeDream    → Generate one image per scene (text-to-image)
Step 3: Seedance 1.5→ Animate each image into a video (image-to-video)
Step 4: Save all outputs neatly under an output folder

Usage:
    python3 storyboard_workflow.py
"""

import os
import time
import json
import base64
import requests
import anthropic

# ──────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────
ANTHROPIC_API_KEY   = os.environ.get("ANTHROPIC_API_KEY", "YOUR_ANTHROPIC_KEY_HERE")
ARK_API_KEY         = #""
SEEDANCE_ENDPOINT   = #""   # Seedance 1.5 inference endpoint
SEEDREAM_MODEL      = #""        # SeeDream 5.0 text-to-image model (latest)

ARK_BASE_URL        = #""
ARK_HEADERS         = {
    "Authorization": f"Bearer {ARK_API_KEY}",
    "Content-Type":  "application/json",
}

OUTPUT_DIR          = "storyboard_output"
NUM_SCENES          = 4      # How many scenes to generate
VIDEO_DURATION      = 5      # Seconds per scene video (4 or 8)
VIDEO_RESOLUTION    = "720p" # "720p" or "1080p"


# ──────────────────────────────────────────────
# STEP 1 — Generate Storyboard with Claude
# ──────────────────────────────────────────────
def generate_storyboard(story_idea: str, num_scenes: int = NUM_SCENES) -> list[dict]:
    """
    Send the story idea to Claude and get back a structured storyboard.
    Returns a list of dicts: [{scene, image_prompt, video_prompt}, ...]
    """
    print(f"\n{'='*50}")
    print(f"STEP 1: Generating {num_scenes}-scene storyboard with Claude...")
    print(f"{'='*50}")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    system_prompt = """You are a professional storyboard writer for cinematic AI video projects.
Given a story idea, break it into scenes and return ONLY a valid JSON array.
Each scene must have:
  - "scene_number": int
  - "scene_title": short title (5 words max)
  - "image_prompt": detailed prompt for a still image generator (describe lighting, composition, style, mood)
  - "video_prompt": short action/motion prompt for animating that image into a 5-second video clip

Respond with ONLY the JSON array, no markdown, no explanation."""

    user_message = f"""Story idea: {story_idea}

Generate exactly {num_scenes} scenes as a JSON array."""

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2048,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = message.content[0].text.strip()

    # Parse JSON safely
    try:
        storyboard = json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract JSON array if wrapped in extra text
        start = raw.find("[")
        end   = raw.rfind("]") + 1
        storyboard = json.loads(raw[start:end])

    print(f"✅ Storyboard created with {len(storyboard)} scenes:")
    for scene in storyboard:
        print(f"   Scene {scene['scene_number']}: {scene['scene_title']}")

    return storyboard


# ──────────────────────────────────────────────
# STEP 2 — Generate Image with SeeDream (text-to-image)
# ──────────────────────────────────────────────
def generate_image(image_prompt: str, output_path: str) -> str:
    """
    Call SeeDream text-to-image API and save the image locally.
    Returns the local file path.
    """
    url     = f"{ARK_BASE_URL}/images/generations"
    payload = {
        "model":           SEEDREAM_MODEL,
        "prompt":          image_prompt,
        "size":            "1280x720",   # 16:9 for video
        "response_format": "b64_json",  # get base64 back directly
    }

    response = requests.post(url, json=payload, headers=ARK_HEADERS)
    response.raise_for_status()
    data = response.json()

    # Decode and save image
    img_b64  = data["data"][0]["b64_json"]
    img_bytes = base64.b64decode(img_b64)
    with open(output_path, "wb") as f:
        f.write(img_bytes)

    print(f"   🖼  Image saved: {output_path}")
    return output_path


# ──────────────────────────────────────────────
# STEP 3 — Animate Image with Seedance 1.5 (image-to-video)
# ──────────────────────────────────────────────
def upload_image_and_get_url(image_path: str) -> str:
    """
    If image is local, we need a public URL for Seedance.
    Simple approach: read as base64 data URI (supported by some endpoints)
    or upload to TOS. Here we use a base64 data URI.
    """
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:image/jpeg;base64,{b64}"


def submit_image_to_video(image_url: str, video_prompt: str) -> str:
    """Submit image-to-video task to Seedance 1.5 and return task ID."""
    url     = f"{ARK_BASE_URL}/contents/generations/tasks"
    payload = {
        "model": SEEDANCE_ENDPOINT,
        "content": [
            {"type": "image_url", "image_url": {"url": image_url}},
            {"type": "text",      "text":      video_prompt},
        ],
        "parameters": {
            "duration":    VIDEO_DURATION,
            "resolution":  VIDEO_RESOLUTION,
            "aspect_ratio": "16:9",
        },
    }
    response = requests.post(url, json=payload, headers=ARK_HEADERS)
    response.raise_for_status()
    task_id = response.json()["id"]
    print(f"   🎬 Video task submitted: {task_id}")
    return task_id


def poll_video_task(task_id: str, interval: int = 10, timeout: int = 300) -> dict:
    """Poll until the video task succeeds or fails."""
    url     = f"{ARK_BASE_URL}/contents/generations/tasks/{task_id}"
    elapsed = 0
    while elapsed < timeout:
        response = requests.get(url, headers=ARK_HEADERS)
        response.raise_for_status()
        data   = response.json()
        status = data.get("status")
        print(f"   ⏳ Status: {status} ({elapsed}s elapsed)", end="\r")

        if status == "succeeded":
            print(f"   ✅ Status: succeeded ({elapsed}s elapsed)      ")
            return data
        if status == "failed":
            raise RuntimeError(f"Task failed: {data.get('error')}")

        time.sleep(interval)
        elapsed += interval

    raise TimeoutError(f"Task {task_id} did not complete within {timeout}s")


def download_video(result: dict, output_path: str) -> str:
    """Download the generated video and save locally."""
    video_url = result["content"]["video_url"]
    response  = requests.get(video_url, stream=True)
    response.raise_for_status()
    with open(output_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    print(f"   💾 Video saved: {output_path}")
    return output_path


# ──────────────────────────────────────────────
# MAIN WORKFLOW
# ──────────────────────────────────────────────
def run_workflow(story_idea: str):
    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ── STEP 1: Storyboard ──
    storyboard = generate_storyboard(story_idea)

    # Save storyboard JSON for reference
    storyboard_path = os.path.join(OUTPUT_DIR, "storyboard.json")
    with open(storyboard_path, "w") as f:
        json.dump(storyboard, f, indent=2)
    print(f"\n📋 Storyboard saved: {storyboard_path}")

    results = []

    for scene in storyboard:
        scene_num   = scene["scene_number"]
        scene_title = scene["scene_title"].replace(" ", "_")
        img_prompt  = scene["image_prompt"]
        vid_prompt  = scene["video_prompt"]

        print(f"\n{'='*50}")
        print(f"SCENE {scene_num}: {scene['scene_title']}")
        print(f"{'='*50}")

        # ── STEP 2: Generate Image ──
        print(f"\n📷 STEP 2: Generating image...")
        img_path = os.path.join(OUTPUT_DIR, f"scene_{scene_num:02d}_{scene_title}.jpg")
        generate_image(img_prompt, img_path)

        # ── STEP 3: Animate to Video ──
        print(f"\n🎬 STEP 3: Animating image to video...")
        image_url  = upload_image_and_get_url(img_path)
        task_id    = submit_image_to_video(image_url, vid_prompt)
        result     = poll_video_task(task_id)
        vid_path   = os.path.join(OUTPUT_DIR, f"scene_{scene_num:02d}_{scene_title}.mp4")
        download_video(result, vid_path)

        results.append({
            "scene":       scene_num,
            "title":       scene["scene_title"],
            "image":       img_path,
            "video":       vid_path,
            "task_id":     task_id,
        })

    # ── SUMMARY ──
    print(f"\n{'='*50}")
    print("✅ WORKFLOW COMPLETE!")
    print(f"{'='*50}")
    print(f"Output folder: {OUTPUT_DIR}/")
    for r in results:
        print(f"  Scene {r['scene']}: {r['title']}")
        print(f"    Image → {r['image']}")
        print(f"    Video → {r['video']}")

    return results


# ──────────────────────────────────────────────
# RUN
# ──────────────────────────────────────────────
if __name__ == "__main__":
    story_idea = """
    A lone surfer discovers a magical glowing wave at dawn.
    She paddles out through morning mist, catches the wave,
    and is transported to an underwater world of light and color,
    before washing ashore on a pristine tropical beach at sunset.
    """

    run_workflow(story_idea)
