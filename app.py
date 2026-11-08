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


# --- 1. 自動改行（手動改行 \n を尊重する）関数 ---
def wrap_text(text, font, max_width):
    # 最初に \n（改行）で文章を分割
    paragraphs = text.split('\n')
    wrapped_lines = []
    for paragraph in paragraphs:
        current_line = ""
        for char in paragraph:
            test_line = current_line + char
            bbox = font.getbbox(test_line)
            if bbox[2] - bbox[0] <= max_width:
                current_line = test_line
            else:
                wrapped_lines.append(current_line)
                current_line = char
        if current_line:
            wrapped_lines.append(current_line)
    return "\n".join(wrapped_lines)


# 裏側（バックグラウンド）で動画処理を行い、完了後にWebhookへ通知する関数
def process_video_background(video_url, text, webhook_url):
    temp_input = None
    try:
        print("バックグラウンドで動画処理を開始します...")
        
        # 1. 動画ファイルを一時的にダウンロード
        response = requests.get(video_url, stream=True)
        response.raise_for_status()
        
        temp_input = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
        for chunk in response.iter_content(chunk_size=8192):
            temp_input.write(chunk)
        temp_input.close()

        # 2. OpenCVで動画を読み込み
        cap = cv2.VideoCapture(temp_input.name)
        if not cap.isOpened():
            raise Exception("動画ファイルを開けませんでした。")

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps == 0 or np.isnan(fps):
            fps = 30.0

        # 出力ファイルの設定
        output_filename = f"processed_{os.path.basename(temp_input.name)}.mp4"
        output_path = os.path.join(OUTPUT_DIR, output_filename)

        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

        # --- 2. フォント設定 ---
        font_size = int(height * 0.05)  # 文字の大きさ
        try:
            font = ImageFont.truetype("NotoSansJP-Bold.ttf", font_size)
        except Exception as e:
            print(f"フォント読み込み失敗、デフォルトを使用します: {e}")
            font = ImageFont.load_default()

        # 画面幅の80%以内に収まるよう自動改行
        max_width = int(width * 0.8)
        wrapped_text = wrap_text(text, font, max_width)

        # --- 3. 動画フレーム処理 ---
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            
            # OpenCV(BGR) -> PIL(RGB)
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img_pil = Image.fromarray(frame_rgb)
            draw = ImageDraw.Draw(img_pil)

            # テキスト全体の位置を計算（画面中央に配置）
            bbox = draw.multiline_textbbox((0, 0), wrapped_text, font=font, align="center")
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            x = (width - text_w) / 2
            y = (height - text_h) / 2

            # 白文字＋黒フチで描画
            draw.multiline_text(
                (x, y),
                wrapped_text,
                font=font,
                fill=(255, 255, 255),  # 文字色：白
                stroke_width=3,        # 黒い縁取りの太さ
                stroke_fill=(0, 0, 0), # 縁取りの色：黒
                align="center"         # 中央揃え
            )

            # PIL(RGB) -> OpenCV(BGR)
            frame_bgr = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
            out.write(frame_bgr)

        cap.release()
        out.release()

        # Render等の公開URLを自動取得（環境変数がない場合はデフォルトURLを使用）
        server_base_url = os.environ.get("RENDER_EXTERNAL_URL", "https://video-text-server-3.onrender.com")
        completed_video_url = f"{server_base_url}/static/{output_filename}"

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
        if webhook_url:
            try:
                requests.post(webhook_url, json={"status": "error", "message": str(e)})
            except:
                pass
    finally:
        # 一時入力ファイルの削除
        if temp_input and os.path.exists(temp_input.name):
            try:
                os.remove(temp_input.name)
            except:
                pass


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
        
        return jsonify({
            "status": "accepted",
            "message": "Video processing started in background."
        }), 200
    else:
        return jsonify({"error": "webhook_url is required"}), 400


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
