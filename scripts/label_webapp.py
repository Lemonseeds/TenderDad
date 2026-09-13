import os
import time
import glob
import random
from flask import Flask, request, render_template_string, redirect, url_for, send_file

app = Flask(__name__)

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(BASE_DIR, "captcha_dataset_raw")
DONE_DIR = os.path.join(BASE_DIR, "captcha_dataset")

os.makedirs(RAW_DIR, exist_ok=True)
os.makedirs(DONE_DIR, exist_ok=True)

# Keep track of images currently being labeled by someone so we don't serve duplicates
in_progress = set()

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>CAPTCHA Labeler</title>
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
        input[type="text"]::placeholder {
            color: rgba(255, 255, 255, 0.2);
            letter-spacing: 1px;
            font-weight: 400;
            font-size: 18px;
        }
        button { 
            font-family: 'Outfit', sans-serif;
            font-weight: 600;
            font-size: 18px; 
            padding: 15px; 
            width: 100%;
            background: linear-gradient(135deg, #e94560 0%, #c12b43 100%); 
            color: white; 
            border: none; 
            border-radius: 12px; 
            cursor: pointer; 
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(233, 69, 96, 0.3);
        }
        button:hover { 
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(233, 69, 96, 0.5);
            background: linear-gradient(135deg, #ff5c77 0%, #d6334d 100%); 
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
            border-color: rgba(255, 255, 255, 0.4);
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
        <h2>TENDERDAD LABELER</h2>
        {% if filename %}
            <img src="{{ url_for('get_image', filename=filename) }}" alt="CAPTCHA">
            <form method="POST" action="{{ url_for('submit', filename=filename) }}">
                <input type="text" name="label" autofocus autocomplete="off" required placeholder="TYPE TEXT HERE..." maxlength="6">
                <button type="submit">Submit Label</button>
            </form>
            <form method="POST" action="{{ url_for('skip', filename=filename) }}">
                <button type="submit" class="skip">Skip (Unreadable)</button>
            </form>
        {% else %}
            <div class="fireworks">🎉</div>
            <h3 style="margin-top:0; font-weight: 600;">You are a legend!</h3>
            <p style="color: rgba(255,255,255,0.6);">All CAPTCHAs have been perfectly labeled.</p>
        {% endif %}
        <div class="stats">
            <div>Remaining: <span>{{ remaining }}</span></div>
            <div>Labeled: <span>{{ completed }}</span></div>
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

def get_stats():
    raw_files = glob.glob(os.path.join(RAW_DIR, "*.png"))
    done_files = glob.glob(os.path.join(DONE_DIR, "*.png"))
    return len(raw_files), len(done_files)

@app.route("/")
def index():
    raw_files = [os.path.basename(f) for f in glob.glob(os.path.join(RAW_DIR, "*.png"))]
    
    # Filter out files currently being worked on by other friends
    available_files = [f for f in raw_files if f not in in_progress]
    
    remaining, completed = get_stats()
    
    if not available_files:
        return render_template_string(HTML_TEMPLATE, filename=None, remaining=remaining, completed=completed)
        
    # Pick a random file for this user to prevent race conditions if friends load page at exact same ms
    filename = random.choice(available_files)
    in_progress.add(filename)
    
    return render_template_string(HTML_TEMPLATE, filename=filename, remaining=remaining, completed=completed)

@app.route("/img/<filename>")
def get_image(filename):
    return send_file(os.path.join(RAW_DIR, filename))

@app.route("/submit/<filename>", methods=["POST"])
def submit(filename):
    label = request.form.get("label", "").strip()
    
    # Release the lock on this file
    if filename in in_progress:
        in_progress.remove(filename)
        
    old_path = os.path.join(RAW_DIR, filename)
    if os.path.exists(old_path) and len(label) > 0:
        # Save it!
        new_filename = f"{label}_{int(time.time()*1000)}.png"
        new_path = os.path.join(DONE_DIR, new_filename)
        os.rename(old_path, new_path)
        
    return redirect(url_for("index"))

@app.route("/skip/<filename>", methods=["POST"])
def skip(filename):
    if filename in in_progress:
        in_progress.remove(filename)
        
    # Just delete it if it's unreadable
    old_path = os.path.join(RAW_DIR, filename)
    if os.path.exists(old_path):
        os.remove(old_path)
        
    return redirect(url_for("index"))

if __name__ == "__main__":
    print(f"Starting web server. Make sure you have raw images in {RAW_DIR}")
    app.run(host="0.0.0.0", port=5000, threaded=True)
