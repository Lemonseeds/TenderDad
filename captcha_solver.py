import os
import re
import threading
import torch
import torch.nn as nn
from torchvision import transforms
from PIL import Image
import io

# --- Custom CRNN Model Definition ---
ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
NUM_CLASSES = len(ALPHABET) + 1 # +1 for CTC blank token

class CRNN(nn.Module):
    def __init__(self, num_classes):
        super(CRNN, self).__init__()
        
        self.cnn = nn.Sequential(
            nn.Conv2d(1, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(),
            nn.MaxPool2d(2, 2),
            
            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(),
            nn.MaxPool2d(2, 2),
            
            nn.Conv2d(64, 128, kernel_size=3, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(),
            nn.MaxPool2d((2, 1), (2, 1)),
            
            nn.Conv2d(128, 256, kernel_size=3, padding=1),
            nn.BatchNorm2d(256),
            nn.ReLU(),
            nn.MaxPool2d((2, 1), (2, 1))
        )
        
        self.rnn = nn.GRU(256 * 3, 128, bidirectional=True, num_layers=2, batch_first=True)
        self.fc = nn.Linear(256, num_classes)

    def forward(self, x):
        conv = self.cnn(x)
        batch, c, h, w = conv.size()
        conv = conv.view(batch, c * h, w)
        conv = conv.permute(0, 2, 1)
        rnn_out, _ = self.rnn(conv)
        out = self.fc(rnn_out)
        
        import torch.nn.functional as F
        out = F.log_softmax(out, dim=2)
        out = out.permute(1, 0, 2)
        return out

# --- Initialize Custom OCR Model ---
print("[CAPTCHA] Loading custom PyTorch CRNN model...")
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "custom_ocr.pth")
model = CRNN(NUM_CLASSES).to(device)
if os.path.exists(MODEL_PATH):
    model.load_state_dict(torch.load(MODEL_PATH, map_location=device, weights_only=True))
model.eval()

transform = transforms.Compose([
    transforms.Resize((48, 128)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.5], std=[0.5])
])

# Lock to ensure thread-safe PyTorch inference
model_lock = threading.Lock()

def decode_ctc(preds):
    """Decodes CTC output into a string using greedy decoding."""
    # preds: (Time, Batch)
    preds = preds[:, 0].cpu().numpy()
    result = []
    prev_char = None
    for p in preds:
        if p != NUM_CLASSES - 1 and p != prev_char: # Not blank and not duplicate
            result.append(ALPHABET[p])
        prev_char = p
    return "".join(result)

def solve_captcha(page, image_selector: str = 'img#captchaImage') -> tuple[str, bytes]:
    """
    Screenshots the CAPTCHA image and solves it instantly using the custom CRNN PyTorch model.
    Returns: (sanitized_captcha_text, raw_image_bytes)
    """
    try:
        captcha_img = page.locator(image_selector)

        if captcha_img.count() == 0:
            print("[CAPTCHA] Could not find CAPTCHA image element.")
            return "", b""

        # 1. Screenshot the CAPTCHA element
        raw_img_bytes = captcha_img.screenshot()
        
        # 2. Preprocess
        image = Image.open(io.BytesIO(raw_img_bytes)).convert('L')
        tensor = transform(image).unsqueeze(0).to(device)
        
        # 3. Inference
        with model_lock:
            with torch.no_grad():
                outputs = model(tensor)
                # outputs: (Time, Batch, Classes)
                preds = outputs.argmax(2) # (Time, Batch)
                
        # 4. Decode
        guess = decode_ctc(preds)
        
        # 5. Sanitize
        submit_text = re.sub(r'[^a-zA-Z0-9]', '', guess)
        
        if len(submit_text) > 0:
            print(f"[CAPTCHA] Solved via Custom Model: '{submit_text}'")
            return submit_text, raw_img_bytes
            
        return "", b""

    except Exception as e:
        print(f"[CAPTCHA] Error solving CAPTCHA: {e}")
        return "", b""
