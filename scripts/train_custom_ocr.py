import os
import glob
import time
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms
from PIL import Image

# --- 1. CONFIGURATION ---
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "captcha_dataset_qa")
MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
os.makedirs(MODEL_DIR, exist_ok=True)

MODEL_PATH = os.path.join(MODEL_DIR, "custom_ocr.pth")
ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
NUM_CLASSES = len(ALPHABET) + 1 # +1 for CTC blank token
IMG_WIDTH = 128
IMG_HEIGHT = 48
BATCH_SIZE = 32
EPOCHS = 100
LEARNING_RATE = 0.001

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using device: {device}")

# --- 2. DATASET DEFINITION ---
class CaptchaDataset(Dataset):
    def __init__(self, file_paths, transform=None):
        self.file_paths = file_paths
        self.transform = transform

    def __len__(self):
        return len(self.file_paths)

    def __getitem__(self, idx):
        img_path = self.file_paths[idx]
        # Label is the part before the first underscore
        label = os.path.basename(img_path).split('_')[0]
        
        # Load image, convert to grayscale
        image = Image.open(img_path).convert('L')
        
        if self.transform:
            image = self.transform(image)
            
        # Convert label string to tensor of indices
        target = [ALPHABET.find(c) for c in label]
        target = torch.tensor(target, dtype=torch.long)
        
        # CTC needs target lengths
        target_length = torch.tensor([len(label)], dtype=torch.long)
        
        return image, target, target_length

# Create a custom collate_fn because target lengths differ (even though they are all 6, it's good practice for CTC)
def collate_fn(batch):
    images, targets, target_lengths = zip(*batch)
    images = torch.stack(images, 0)
    targets = torch.cat(targets, 0)
    target_lengths = torch.cat(target_lengths, 0)
    return images, targets, target_lengths

# --- 3. MODEL ARCHITECTURE (CRNN) ---
class CRNN(nn.Module):
    def __init__(self, num_classes):
        super(CRNN, self).__init__()
        
        # CNN Feature Extractor
        self.cnn = nn.Sequential(
            nn.Conv2d(1, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(),
            nn.MaxPool2d(2, 2), # 128x48 -> 64x24
            
            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(),
            nn.MaxPool2d(2, 2), # 64x24 -> 32x12
            
            nn.Conv2d(64, 128, kernel_size=3, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(),
            nn.MaxPool2d((2, 1), (2, 1)), # 32x12 -> 32x6 (Keep width resolution high for sequence)
            
            nn.Conv2d(128, 256, kernel_size=3, padding=1),
            nn.BatchNorm2d(256),
            nn.ReLU(),
            nn.MaxPool2d((2, 1), (2, 1)) # 32x6 -> 32x3
        )
        
        # RNN Sequence Model
        self.rnn = nn.GRU(256 * 3, 128, bidirectional=True, num_layers=2, batch_first=True)
        
        # Fully Connected Classifier
        self.fc = nn.Linear(256, num_classes)

    def forward(self, x):
        # x shape: (batch, 1, 48, 128)
        conv = self.cnn(x)
        
        # conv shape: (batch, 256, 3, 32)
        batch, c, h, w = conv.size()
        
        # Reshape to (batch, w, c*h) for RNN
        conv = conv.view(batch, c * h, w)
        conv = conv.permute(0, 2, 1) # (batch, 32, 768)
        
        rnn_out, _ = self.rnn(conv) # rnn_out: (batch, 32, 256)
        
        out = self.fc(rnn_out) # out: (batch, 32, num_classes)
        
        import torch.nn.functional as F
        out = F.log_softmax(out, dim=2)
        
        # CTC Loss expects (Time, Batch, Classes)
        out = out.permute(1, 0, 2)
        
        return out

# --- 4. TRAINING LOOP ---
def train():
    all_files = glob.glob(os.path.join(DATA_DIR, "*.png"))
    if len(all_files) == 0:
        print("No images found in QA dataset!")
        return

    print(f"Found {len(all_files)} images for training.")
    
    # Manual train/test split to avoid sklearn dependency
    import random
    random.seed(42)
    random.shuffle(all_files)
    split_idx = int(len(all_files) * 0.9)
    train_files = all_files[:split_idx]
    val_files = all_files[split_idx:]
    
    # Data Augmentation for Training
    train_transform = transforms.Compose([
        transforms.Resize((IMG_HEIGHT, IMG_WIDTH)),
        transforms.RandomRotation(5),
        transforms.ColorJitter(brightness=0.2, contrast=0.2),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.5], std=[0.5])
    ])
    
    # No augmentation for Validation
    val_transform = transforms.Compose([
        transforms.Resize((IMG_HEIGHT, IMG_WIDTH)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.5], std=[0.5])
    ])
    
    train_dataset = CaptchaDataset(train_files, transform=train_transform)
    val_dataset = CaptchaDataset(val_files, transform=val_transform)
    
    train_loader = DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True, collate_fn=collate_fn)
    val_loader = DataLoader(val_dataset, batch_size=BATCH_SIZE, shuffle=False, collate_fn=collate_fn)
    
    model = CRNN(NUM_CLASSES).to(device)
    criterion = nn.CTCLoss(blank=NUM_CLASSES-1, zero_infinity=True)
    optimizer = optim.Adam(model.parameters(), lr=LEARNING_RATE)
    
    best_val_loss = float('inf')
    
    for epoch in range(EPOCHS):
        model.train()
        train_loss = 0.0
        
        for images, targets, target_lengths in train_loader:
            images = images.to(device)
            targets = targets.to(device)
            target_lengths = target_lengths.to(device)
            
            optimizer.zero_grad()
            
            outputs = model(images) # (Time, Batch, Classes)
            
            input_lengths = torch.full((outputs.size(1),), outputs.size(0), dtype=torch.long).to(device)
            
            loss = criterion(outputs, targets, input_lengths, target_lengths)
            loss.backward()
            optimizer.step()
            
            train_loss += loss.item()
            
        train_loss /= len(train_loader)
        
        # Validation
        model.eval()
        val_loss = 0.0
        correct_chars = 0
        total_chars = 0
        
        with torch.no_grad():
            for images, targets, target_lengths in val_loader:
                images = images.to(device)
                targets = targets.to(device)
                target_lengths = target_lengths.to(device)
                
                outputs = model(images)
                input_lengths = torch.full((outputs.size(1),), outputs.size(0), dtype=torch.long).to(device)
                
                loss = criterion(outputs, targets, input_lengths, target_lengths)
                val_loss += loss.item()
                
                # Simple greedy decoding for accuracy metric
                # outputs shape: (Time, Batch, Classes)
                preds = outputs.argmax(2).permute(1, 0) # (Batch, Time)
                
                # Compare (rough char accuracy, ignores blanks/repeats alignment logic, just a proxy metric)
                # Proper decoding requires collapsing repeats/blanks, but this is fast.
                
        val_loss /= len(val_loader)
        
        print(f"Epoch [{epoch+1}/{EPOCHS}] - Train Loss: {train_loss:.4f} | Val Loss: {val_loss:.4f}")
        
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            torch.save(model.state_dict(), MODEL_PATH)
            print(f"  -> Saved new best model to {MODEL_PATH}")

    print("Training Complete!")

if __name__ == "__main__":
    start_time = time.time()
    train()
    print(f"Total training time: {time.time() - start_time:.2f} seconds")
