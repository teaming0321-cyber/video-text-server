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

# --- 1. 自動改行（画面幅に収める）関数 ---
    def wrap_text(text, font, max_width):
        lines = []
        current_line = ""
        for char in text:
            test_line = current_line + char
            bbox = font.getbbox(test_line)
            if bbox[2] - bbox[0] <= max_width:
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = char
        if current_line:
            lines.append(current_line)
        return "\n".join(lines)

    # --- 2. フォント設定 ---
    font_size = int(height * 0.05)  # 文字の大きさ
    try:
        font = ImageFont.truetype("NotoSansJP-Bold.ttf", font_size)
    except:
        font = ImageFont.load_default()

    # 画面幅の80%以内に収まるよう自動改行
    wrapped_text = wrap_text(text, font, int(width * 0.8))

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

        # ★ 黒枠（draw.rectangle）は削除し、白文字＋黒フチで描画
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
