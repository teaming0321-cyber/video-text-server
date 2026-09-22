import os
import tempfile
import requests
import cv2
import numpy as np
from flask import Flask, request, jsonify, send_from_directory
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)
OUTPUT_DIR = "static"
os.makedirs(OUTPUT_DIR, exist_ok=True)

@app.route('/')
def home():
    return "Video Text Overlay Server is Running!"

@app.route('/process', methods=['POST', 'GET'])
def process_video():
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        video_url = data.get('video_url') or request.values.get('video_url')
        text = data.get('text') or request.values.get('text')
    else:
        video_url = request.args.get('video_url')
        text = request.args.get('text')

    if not video_url or not text:
        return jsonify({"status": "error", "message": "video_url and text are required"}), 400

    try:
        # 1. 元動画のダウンロード
        resp = requests.get(video_url, stream=True)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp_in:
            for chunk in resp.iter_content(chunk_size=1024*1024):
                if chunk:
                    tmp_in.write(chunk)
            input_path = tmp_in.name

        # 2. 動画の読み込みと文字入れ設定
        cap = cv2.VideoCapture(input_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        output_filename = f"output_{os.urandom(4).hex()}.mp4"
        output_path = os.path.join(OUTPUT_DIR, output_filename)

        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

        # フォント設定 (デフォルトフォント)
        font_size = int(height * 0.05)
        try:
            font = ImageFont.truetype("NotoSansJP-Bold.ttf", font_size)
        except:
            font = ImageFont.load_default()

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            # BGRからRGB変換してPIL Imageへ
            img_pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(img_pil)

            # テキストサイズの計算と中央下部への配置
            bbox = draw.textbbox((0, 0), text, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            x = (width - text_w) // 2
            y = int(height * 0.8) - text_h // 2

            # 背景座布団（見やすくするための黒枠）
            margin = 15
            draw.rectangle([x - margin, y - margin, x + text_w + margin, y + text_h + margin], fill=(0, 0, 0, 160))
            # 白文字の描画
            draw.text((x, y), text, font=font, fill=(255, 255, 255))

            # フレーム書き込み
            frame_out = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
            out.write(frame_out)

        cap.release()
        out.release()
        os.remove(input_path)

        # ドメインURLの自動作成
        host_url = request.host_url.rstrip('/')
        final_video_url = f"{host_url}/static/{output_filename}"

        return jsonify({
            "status": "success",
            "video_url": final_video_url
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/static/<filename>')
def serve_file(filename):
    return send_from_directory(OUTPUT_DIR, filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
