import os
import time
import requests

API_KEY = "ark-6eda8d70-3533-4146-a8c3-e96325b9c3e4-08dc9"
ENDPOINT_ID = "ep-20260608171120-mvkcn"
BASE_URL = "https://ark.ap-southeast.bytepluses.com/api/v3"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}


def submit_text_to_video(prompt: str, duration: int = 5, resolution: str = "1080p") -> str:
    """Submit a text-to-video generation task and return the task ID."""
    url = f"{BASE_URL}/contents/generations/tasks"
    payload = {
        "model": ENDPOINT_ID,
        "content": [
            {
                "type": "text",
                "text": prompt,
            }
        ],
        "parameters": {
            "duration": duration,
            "resolution": resolution,
            "aspect_ratio": "16:9",
        },
    }
    response = requests.post(url, json=payload, headers=HEADERS)
    response.raise_for_status()
    data = response.json()
    task_id = data["id"]
    print(f"Task submitted. ID: {task_id}")
    return task_id


def submit_image_to_video(image_url: str, prompt: str, duration: int = 5, resolution: str = "1080p") -> str:
    """Submit an image-to-video generation task and return the task ID."""
    url = f"{BASE_URL}/contents/generations/tasks"
    payload = {
        "model": ENDPOINT_ID,
        "content": [
            {
                "type": "image_url",
                "image_url": {"url": image_url},
            },
            {
                "type": "text",
                "text": prompt,
            },
        ],
        "parameters": {
            "duration": duration,
            "resolution": resolution,
            "aspect_ratio": "16:9",
        },
    }
    response = requests.post(url, json=payload, headers=HEADERS)
    response.raise_for_status()
    data = response.json()
    task_id = data["id"]
    print(f"Task submitted. ID: {task_id}")
    return task_id


def poll_task(task_id: str, interval: int = 10, timeout: int = 300) -> dict:
    """Poll until the task succeeds or fails."""
    url = f"{BASE_URL}/contents/generations/tasks/{task_id}"
    elapsed = 0
    while elapsed < timeout:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        status = data.get("status")
        print(f"Status: {status} ({elapsed}s elapsed)")

        if status == "succeeded":
            return data
        if status == "failed":
            raise RuntimeError(f"Task failed: {data.get('error')}")

        time.sleep(interval)
        elapsed += interval

    raise TimeoutError(f"Task did not complete within {timeout}s")


def download_video(result: dict, output_path: str = "output.mp4") -> None:
    """Download the generated video from the result."""
    content = result.get("content", {})
    video_url = content.get("video_url")

    if not video_url:
        print("Full result:", result)
        raise ValueError("No video URL found in result.")

    print(f"Downloading video from: {video_url}")
    video_response = requests.get(video_url, stream=True)
    video_response.raise_for_status()
    with open(output_path, "wb") as f:
        for chunk in video_response.iter_content(chunk_size=8192):
            f.write(chunk)
    print(f"Video saved to: {output_path}")


if __name__ == "__main__":
    image_url = "https://kristin.tos-ap-southeast-1.bytepluses.com/IMG_3815%202.JPG"
    prompt = "create a slow motion cinematic scene of surfing videos"

    task_id = submit_image_to_video(image_url, prompt, duration=5, resolution="1080p")
    result = poll_task(task_id)
    download_video(result, output_path="Kristin_surfing.mp4")
