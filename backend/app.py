import shutil
from datetime import time, timedelta
import json
import os
import time
from pathlib import Path

from vtt_to_srt import vtt_to_srt

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from yt_dlp import YoutubeDL
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import requests

import utils

load_dotenv('.env')

app = Flask(__name__)

WOMBO_API_KEY = os.getenv('WOMBO_API_KEY')
API_URL = "https://api.luan.tools/api"
FRAMERATE = 12
NEW_IMAGE_WEIGHT = 0.09
GENERATOR_BATCH_SIZE = 20

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
    command = f"ffmpeg -r {FRAMERATE} -i ./working/{project_id}/%d.jpg -i ./working/{project_id}/audio.m4a ./static/{project_id}.mp4"
    os.system(f'cmd /c "{command}"')


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


def get_many_tasks(tasks: [str], job_id, num_start=2):
    res = [-1] * len(tasks)  # -1 is sentinel num, that nothing has happened yet

    while -1 in res:
        for ind, task in enumerate(tasks):
            if res[ind] != -1:
                continue

            task_id_url = f"https://api.luan.tools/api/tasks/{task['id']}"
            response_json = requests.request(
                "GET", task_id_url, headers=HEADERS).json()

            state = response_json["state"]

            if state == "completed":
                r = requests.request("GET", response_json["result"])
                url = f"working/{job_id}/{num_start + ind}.jpg"
                with open(f"./{url}", "wb") as image_file:
                    image_file.write(r.content)
                print(f"image saved successfully {ind}")
                res[ind] = url
            elif state == "failed":
                print(f"generation failed {ind} :(", json.dumps(response_json))
                res[ind] = False

        time.sleep(3)

    return res


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


def download_video(url: str, project_id: str):
    print("attempting to download ", url, ' for ', project_id)
    ydl_opts = {
        'outtmpl': f'./working/{project_id}/audio.m4a',
        'format': 'm4a/bestaudio/best',
        'writesubtitles': True,
        'subtitle': '--write-sub',
        "writeautomaticsub": True,
        # 'subtitleslangs': ['en'],
        # ℹ️ See help(yt_dlp.postprocessor) for a list of available Postprocessors and their arguments
        'postprocessors': [{  # Extract audio using ffmpeg
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'm4a',
        }]
    }

    with YoutubeDL(ydl_opts) as ydl:
        error_code = ydl.download([url])

    return error_code


def multi_img2img(prev_image_path: Path, project_id: str, prompts: [str], style: int, start_num=2):
    print(f"[img2img] {project_id} prompts:{str(prompts)} s:{style} n:{start_num}-{len(prompts)}")

    tasks = []
    for i in range(len(prompts)) :
        print(f"Create task {i}")
        tasks.append(create_new_task(True))

    for i, t in enumerate(tasks):
        print(f"Uploading for {i}")
        target_image_url = t["target_image_url"]
        with open(prev_image_path, 'rb') as f:
            fields = target_image_url["fields"]
            fields["file"] = f.read()
            requests.request("POST", url=target_image_url["url"], files=fields)

    for i, t in enumerate(tasks):
        update_task(t['id'], prompts[i], style=style, target_image_weight=(1 - NEW_IMAGE_WEIGHT))

    res_arr = get_many_tasks(tasks, project_id, start_num)

    for i in range(len(res_arr)):
        if not res_arr[i]:
            shutil.copyfile(prev_image_path, f"working/{project_id}/{start_num + i}.jpg")

    return


def new_img2img(prev_image_path: Path, project_id: str, prompt: str, style: int, num=0):
    print(f"[img2img] prompt:{prompt} s:{style} n:{num}")

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


def process_new_video(project_id: str, style: int, title: str):
    """
       Body Reqs:
        - prompt: str
        - style: int id
       :return:
       """
    num = 0
    res = []

    subfile = None
    files = os.listdir(f'./working/{project_id}')
    for f in files:
        if ".vtt" in f:
            subfile = f

    # vtt_to_srt.vtt_to_srt(f'./working/{project_id}/{subfile}')

    subs = utils.yoink_subtitles(Path(f'./working/{project_id}/{subfile}'), title)
    caps = utils.generate_captions(subs, FRAMERATE)

    # speshal case
    while True:
        print("Generating Image 0")
        res1 = single_image(project_id, caps[0], style)
        if res1:
            res.append(res1)
            break

    num = 0
    while num < len(caps) - 1:
        subset = caps[num: min(num + GENERATOR_BATCH_SIZE, len(caps))]
        multi_img2img(Path(f"./working/{project_id}/{num}.jpg"), project_id, subset, style, num)
        num += len(subset) - 1

    stitch_ffmpeg(project_id)


@app.route('/api/new-video', methods=['POST'])
def new_video():
    data = request.json
    if 'url' not in data:
        return "No prompt config found", 400
    if 'style' not in data:
        return "No style config found", 400
    if 'title' not in data:
        return "No title found", 400

    project_id = str(uuid4())
    err = download_video(data['url'], project_id)

    time.sleep(1)
    if not err:
        process_new_video(project_id, data['style'], data['title'])
        return jsonify({"projectId": project_id})
    else:
        return err, 500


# @app.route('/api/video', methods=['GET'])
# def get_status():
#     data = request.json['id']
#


@app.route('/')
def index():
    return f'Bruh.'


if __name__ == '__main__':
    app.run()
