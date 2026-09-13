import os
import time
import glob
from flask import Flask, request, render_template_string, redirect, url_for, send_file

app = Flask(__name__)

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LABELED_DIR = os.path.join(BASE_DIR, "captcha_dataset")
QA_DIR = os.path.join(BASE_DIR, "captcha_dataset_qa")

os.makedirs(LABELED_DIR, exist_ok=True)
os.makedirs(QA_DIR, exist_ok=True)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Dataset QA Review</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap" rel="stylesheet">
    <style>
        * { box-sizing: border-box; }
        body { 
            font-family: 'Outfit', sans-serif; 
            display: flex; flex-direction: column; align-items: center; justify-content: center; 
            min-height: 100vh; margin: 0; 
            background: linear-gradient(-45deg, #0f0c29, #302b63, #24243e, #1a1a2e);
            background-size: 400% 400%;
            animation: gradientBG 15s ease infinite;
            color: white; 
        }
        @keyframes gradientBG {
            0% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
            100% { background-position: 0% 50%; }
        }
        .container { 
            background: rgba(22, 33, 62, 0.4);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            padding: 40px; 
            border-radius: 24px; 
            border: 1px solid rgba(255, 255, 255, 0.1);
            box-shadow: 0 25px 50px -12px rgba(0,0,0,0.7), 0 0 40px rgba(0, 173, 181, 0.15); 
            text-align: center;
            max-width: 450px;
            width: 90%;
            transform: translateY(0);
            transition: transform 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
        }
        .container:hover {
            transform: translateY(-5px);
        }
        h2 { 
            margin-top: 0; 
            font-weight: 800; 
            font-size: 28px;
            background: linear-gradient(90deg, #00adb5, #e94560);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 25px;
            letter-spacing: 1px;
        }
        img { 
            border: none; 
            border-radius: 12px; 
            margin-bottom: 25px; 
            width: 100%; 
            height: auto; 
            box-shadow: 0 10px 20px rgba(0,0,0,0.3);
            transition: transform 0.3s ease;
        }
        img:hover {
            transform: scale(1.02);
        }
        input[type="text"] { 
            font-family: 'Outfit', sans-serif;
            font-weight: 600;
            font-size: 28px; 
            letter-spacing: 6px;
            padding: 15px; 
            width: 100%; 
            text-align: center; 
            border: 2px solid rgba(255, 255, 255, 0.1); 
            border-radius: 12px; 
            margin-bottom: 20px; 
            outline: none; 
            background: rgba(0, 0, 0, 0.2); 
            color: #fff;
            transition: all 0.3s ease;
        }
        input[type="text"]:focus { 
            border-color: #e94560; 
            box-shadow: 0 0 25px rgba(233, 69, 96, 0.4);
            background: rgba(0, 0, 0, 0.4);
        }
        button { 
            font-family: 'Outfit', sans-serif;
            font-weight: 600;
            font-size: 18px; 
            padding: 15px; 
            width: 100%;
            background: linear-gradient(135deg, #00adb5 0%, #007a82 100%); 
            color: white; 
            border: none; 
            border-radius: 12px; 
            cursor: pointer; 
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(0, 173, 181, 0.3);
        }
        button:hover { 
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(0, 173, 181, 0.5);
            background: linear-gradient(135deg, #00c9d2 0%, #009a9f 100%); 
        }
        button:active {
            transform: translateY(1px);
        }
        .stats { 
            margin-top: 25px; 
            color: rgba(255, 255, 255, 0.5); 
            font-size: 14px;
            font-weight: 300;
            display: flex;
            justify-content: space-between;
            border-top: 1px solid rgba(255, 255, 255, 0.1);
            padding-top: 20px;
        }
        .stats span {
            color: #00adb5;
            font-weight: 600;
        }
        .skip { 
            margin-top: 15px; 
            background: transparent; 
            border: 1px solid rgba(255, 255, 255, 0.2); 
            color: rgba(255, 255, 255, 0.6); 
            box-shadow: none;
        }
        .skip:hover { 
            background: rgba(255, 255, 255, 0.1); 
            color: white; 
            border-color: #e94560;
            box-shadow: none;
        }
        .fireworks {
            font-size: 60px;
            margin-bottom: 20px;
            animation: bounce 2s infinite ease-in-out;
        }
        @keyframes bounce {
            0%, 100% { transform: translateY(0); }
            50% { transform: translateY(-15px); }
        }
    </style>
</head>
<body>
    <div class="container">
        <h2>DATASET QA</h2>
        {% if filename %}
            <img src="{{ url_for('get_image', filename=filename) }}" alt="CAPTCHA">
            <form method="POST" action="{{ url_for('submit', filename=filename) }}">
                <input type="text" name="label" value="{{ default_label }}" autofocus autocomplete="off" required maxlength="6">
                <button type="submit">Approve (Enter)</button>
            </form>
            <form method="POST" action="{{ url_for('discard', filename=filename) }}">
                <button type="submit" class="skip">Discard Image</button>
            </form>
        {% else %}
            <div class="fireworks">🎉</div>
            <h3 style="margin-top:0; font-weight: 600;">QA Complete!</h3>
            <p style="color: rgba(255,255,255,0.6);">All CAPTCHAs have been verified and moved to the QA folder.</p>
            <p style="color: #00adb5; margin-top: 15px;">You are ready to train the model!</p>
        {% endif %}
        <div class="stats">
            <div>Needs QA: <span>{{ remaining }}</span></div>
            <div>Approved: <span>{{ completed }}</span></div>
        </div>
    </div>
    
    <script>
        const input = document.querySelector('input[type="text"]');
        if (input) {
            input.focus();
            document.addEventListener('click', () => input.focus());
        }
    </script>
</body>
</html>
"""

import random

in_progress = set()

def get_stats():
    raw_files = glob.glob(os.path.join(LABELED_DIR, "*.png"))
    qa_files = glob.glob(os.path.join(QA_DIR, "*.png"))
    return len(raw_files), len(qa_files)

@app.route("/")
def index():
    raw_files = [os.path.basename(f) for f in glob.glob(os.path.join(LABELED_DIR, "*.png"))]
    available_files = [f for f in raw_files if f not in in_progress]
    
    remaining, completed = get_stats()
    
    if not available_files:
        return render_template_string(HTML_TEMPLATE, filename=None, remaining=remaining, completed=completed)
        
    filename = random.choice(available_files)
    in_progress.add(filename)
    
    # Extract the label from the filename (e.g., "Ab34D2_1789239334639.png" -> "Ab34D2")
    default_label = filename.split("_")[0]
    
    return render_template_string(HTML_TEMPLATE, filename=filename, default_label=default_label, remaining=remaining, completed=completed)

@app.route("/img/<filename>")
def get_image(filename):
    return send_file(os.path.join(LABELED_DIR, filename))

@app.route("/submit/<filename>", methods=["POST"])
def submit(filename):
    label = request.form.get("label", "").strip()
    
    if filename in in_progress:
        in_progress.remove(filename)
        
    old_path = os.path.join(LABELED_DIR, filename)
    if os.path.exists(old_path) and len(label) > 0:
        # Move it to QA dir with the potentially updated label!
        new_filename = f"{label}_{int(time.time()*1000)}.png"
        new_path = os.path.join(QA_DIR, new_filename)
        os.rename(old_path, new_path)
        
    return redirect(url_for("index"))

@app.route("/discard/<filename>", methods=["POST"])
def discard(filename):
    if filename in in_progress:
        in_progress.remove(filename)
        
    old_path = os.path.join(LABELED_DIR, filename)
    if os.path.exists(old_path):
        os.remove(old_path)
        
    return redirect(url_for("index"))

if __name__ == "__main__":
    print(f"Starting QA web server on port 5001...")
    print(f"Open http://localhost:5001 in your browser to begin QA.")
    app.run(host="0.0.0.0", port=5001, threaded=True)
