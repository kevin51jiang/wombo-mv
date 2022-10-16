import json
import os
import time
from pathlib import Path

from tinydb import TinyDB, Query
from concurrent.futures import ThreadPoolExecutor
from tinyrecord import transaction
from uuid import uuid4
from yt_dlp import YoutubeDL
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import requests

load_dotenv('.env')

app = Flask(__name__)

WOMBO_API_KEY = os.getenv('WOMBO_API_KEY')
API_URL = "https://api.luan.tools/api"
FRAMERATE = 10
db = TinyDB("database.json").table('jobs')
NEW_IMAGE_WEIGHT = 0.0001

HEADERS = {
    'Authorization': f'Bearer {WOMBO_API_KEY}',
    'Content-Type': 'application/json'
}

executor = ThreadPoolExecutor(10)


@app.route('/api/styles', methods=['GET'])
def get_styles():
    """
    Transparently return the listed styles
    :return:
    """
    data = requests.get(f"{API_URL}/styles/", headers=HEADERS).json()
    return jsonify(data)


def stitch_ffmpeg(project_id: str):
    command = f"ffmpeg -r {FRAMERATE} -i ./working/{project_id}/%d.jpg -i audio.m4a ./static/{project_id}/output.mp4"


def create_new_task(use_target_image: bool):
    """
        Sample return 1: {
            "id": "a4a35b0e-3789-40f1-b44b-b32b81e0f3bb",
            "input_spec": null,
            "state": "input",
            "photo_url_list": null,
            "result": null,
            "use_target_image": false,
            "target_image_url": null,
            "created_at": "2022-10-15T13:52:05.375136+00:00",
            "updated_at": "2022-10-15T13:52:05.375143+00:00"
        }

        Sample return 2: {
            "id": "a4a35b0e-3789-40f1-b44b-b32b81e0f3bb",
            "input_spec": null,
            "state": "input",
            "photo_url_list": null,
            "result": null,
            "use_target_image": false,
            "target_image_url": {
                "url": "https://luan-wombo-paint.s3.amazonaws.com/",
                "fields": {
                    "key": "target_images/<task_id>/target.jpg",
                    "AWSAccessKeyId": "AKIADADDDVCE7PD3J",
                    "policy": "eyJDoialkJoiwujIwMjItMDctMjZUMTY6NDQ6NDBaIiwgImNvbmRpdGlvbnMiOiBbeyJidWNrZXQiOiAibHVhbi13b21iby1wYWludCJ9LCB7ImtleSI6ICJ0YXJnZXRfaW1hZ2VzLzE2ODczZmMyLWEzMGYtNDBlNy1iODQ4LTQxNTJjY2ZhMjNiNS90YXJnZXQuanBnIn1dfQ==",
                    "signature": "ddawfvbwM92Fn/L9KrY9yQVsA="
                }
            },
            "created_at": "2022-10-15T13:52:05.375136+00:00",
            "updated_at": "2022-10-15T13:52:05.375143+00:00"
        }

    :param use_target_image:
    :return:
    """

    post_payload = json.dumps({
        "use_target_image": use_target_image
    })
    post_response = requests.request("POST", f"{API_URL}/tasks/", headers=HEADERS, data=post_payload)

    return post_response.json()


def update_task(task_id: str, prompt: str, style=17, target_image_weight=0.1, width=1280, height=720):
    task_id_url = f"https://api.luan.tools/api/tasks/{task_id}"
    put_payload = json.dumps({
        "input_spec": {
            "style": style,
            "prompt": prompt,
            "target_image_weight": target_image_weight,
            "width": width,
            "height": height,
            "seed": "absolutely poggers"
        }})
    ret = requests.request("PUT", task_id_url, headers=HEADERS, data=put_payload).json()
    return ret


def get_task(task_id: str, job_id: str, num=0):
    task_id_url = f"https://api.luan.tools/api/tasks/{task_id}"

    while True:
        response_json = requests.request(
            "GET", task_id_url, headers=HEADERS).json()

        state = response_json["state"]

        if state == "completed":
            r = requests.request("GET", response_json["result"])
            url = f"working/{job_id}/{num}.jpg"
            with open(f"./{url}", "wb") as image_file:
                image_file.write(r.content)
            print("image saved successfully ")
            return url
        elif state == "failed":
            print("generation failed :(", json.dumps(response_json))
            return False

        time.sleep(3)


def download_video(url: str):
    ydl_opts = {
        'outtmpl': './working/audio.m4a',
        'format': 'm4a/bestaudio/best',
        'writesubtitles': True,
        'subtitle': '--write-sub  --sub-langs en',
        # ℹ️ See help(yt_dlp.postprocessor) for a list of available Postprocessors and their arguments
        'postprocessors': [{  # Extract audio using ffmpeg
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'm4a',
        }]
    }

    with YoutubeDL(ydl_opts) as ydl:
        error_code = ydl.download([url])

    return error_code


def new_img2img(prev_image_path: Path, project_id: str, prompt: str, style: int, num=2):
    task = create_new_task(True)
    task_id = task['id']

    target_image_url = task["target_image_url"]
    with open(prev_image_path, 'rb') as f:
        fields = target_image_url["fields"]
        fields["file"] = f.read()
        requests.request("POST", url=target_image_url["url"], files=fields)

    updated_task = update_task(task_id, prompt, style=style, target_image_weight=(1 - NEW_IMAGE_WEIGHT))
    res = get_task(task_id, project_id, num)

    if res:
        # Generated properly
        return res
    else:
        # Failed to generate
        return False


def single_image(project_id: str, prompt: str, style=17):
    task = create_new_task(False)
    task_id = task['id']

    updated_task = update_task(task_id, prompt, style=style)
    res = get_task(task_id, project_id, 0)

    if res:
        # Generated properly
        return res
    else:
        # Failed to generate
        return False


@app.route('/api/new-image', methods=['POST'])
def new_image():
    """
    Body Reqs:
     - prompt: str
     - style: int id
    :return:
    """
    num = 0
    res = []

    data = request.json
    if 'prompt' not in data:
        return "No prompt config found", 400
    if 'style' not in data:
        return "No style config found", 400

    project_id = str(uuid4())

    Path(f"./working/{project_id}").mkdir()

    prompt = data['prompt']
    style = int(data['style'])

    while True:
        print("Generating Image 0")
        res1 = single_image(project_id, prompt, style)
        if res1:
            res.append(res1)
            break

    while num < 10:
        print(f"Generating image {num}")

        new_pic = new_img2img(Path(f"./working/{project_id}/{num}.jpg"), project_id, prompt, style, num + 1)

        if new_pic:
            res.append(new_pic)
            num += 1

    if res:
        # Generated properly
        return jsonify({'result': res})
    else:
        # Failed to generate
        return "Failed to generate", 500


def process_new_video(youtube_id: str, style: int):
    pass


@app.route('/api/new-video', methods=['POST'])
def new_video():
    data = request.json

    data = request.json
    if 'prompt' not in data:
        return "No prompt config found", 400
    if 'style' not in data:
        return "No style config found", 400

    download_video(data['url'])

    return


# @app.route('/api/video', methods=['GET'])
# def get_status():
#     data = request.json['id']
#


@app.route('/')
def index():
    return f'Bruh.'


if __name__ == '__main__':
    app.run()
