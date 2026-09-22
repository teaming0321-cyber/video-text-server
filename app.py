from flask import Flask, request, jsonify, send_from_directory
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import requests
import os
import tempfile

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
        video_url = data.get('video_url')
        text = data.get('text', '')
    else:
        video_url = request.args.get('video_url')
        text = request.args.get('text', '')

    if not video_url:
        return jsonify({"error": "video_url is required"}), 400

    # 一時ファイルの作成
    temp_dir = tempfile.mkdtemp()
    input_path = os.path.join(temp_dir, "input.mp4")
    output_filename = f"output_{os.urandom(4).hex()}.mp4"
    output_path = os.path.join(OUTPUT_DIR, output_filename)

    # 動画のダウンロード
    res = requests.get(video_url, stream=True)
    with open(input_path, 'wb') as f:
        for chunk in res.iter_content(chunk_size=1024*1024):
            if chunk:
                f.write(chunk)

    cap = cv2.VideoCapture(input_path)
    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps    = cap.get(cv2.CAP_PROP_FPS)

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

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

    # --- 2. フォント設定 ---
    font_size = int(height * 0.05)
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

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img_pil = Image.fromarray(frame_rgb)
        draw = ImageDraw.Draw(img_pil)

        bbox = draw.multiline_textbbox((0, 0), wrapped_text, font=font, align="center")
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = (width - text_w) / 2
        y = (height - text_h) / 2

        draw.multiline_text(
            (x, y),
            wrapped_text,
            font=font,
            fill=(255, 255, 255),  # 白文字
            stroke_width=3,        # 黒縁の太さ
            stroke_fill=(0, 0, 0), # 黒縁
            align="center"
        )

        frame_bgr = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
        out.write(frame_bgr)

    cap.release()
    out.release()

    video_url_result = f"{request.host_url.rstrip('/')}/static/{output_filename}"
    return jsonify({"processed_video_url": video_url_result})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
