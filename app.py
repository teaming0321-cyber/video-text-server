import os
import tempfile
import threading
from flask import Flask, jsonify, request, send_from_directory
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import requests

app = Flask(__name__)
OUTPUT_DIR = "static"
os.makedirs(OUTPUT_DIR, exist_ok=True)


@app.route('/')
def home():
    return "Video Text Overlay Server is Running!"


# 裏側（バックグラウンド）で動画処理を行い、完了後にWebhookへ通知する関数
def process_video_background(video_url, text, webhook_url):
    try:
        print("バックグラウンドで動画処理を開始します...")
        
        # --- ここに実際の動画処理（文字入れ等）が入ります ---
        # 処理が完了した動画のURL（テスト時はそのまま受け取ったURL等でもOKです）
        completed_video_url = video_url 

        # 処理が終わったらMakeのWebhookへ通知を送る
        if webhook_url:
            payload = {
                "video_url": completed_video_url,
                "text": text,
                "status": "success"
            }
            res = requests.post(webhook_url, json=payload)
            print(f"Webhook通知完了: {res.status_code}")
            
    except Exception as e:
        print(f"バックグラウンド処理エラー: {e}")


@app.route('/process', methods=['POST', 'GET'])
def process_video():
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        video_url = data.get('video_url')
        text = data.get('text', '')
        webhook_url = data.get('webhook_url')
    else:
        video_url = request.args.get('video_url')
        text = request.args.get('text', '')
        webhook_url = request.args.get('webhook_url')

    if not video_url:
        return jsonify({"error": "video_url is missing"}), 400

    # webhook_url がある場合は非同期（バックグラウンド）で動かし、即座に返事をする
    if webhook_url:
        thread = threading.Thread(
            target=process_video_background,
            args=(video_url, text, webhook_url)
        )
        thread.start()
        
        # ★ここですぐに返事を返すため、Make側のタイムアウトが起きなくなります
        return jsonify({
            "status": "accepted",
            "message": "Video processing started in background."
        }), 200
    else:
        return jsonify({"error": "webhook_url is required"}), 400


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
