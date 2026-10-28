"""
train_crack_model.py - how the crack model (best_v2.pt) was trained.

Training ran on a Google Colab GPU, in two stages:
  1. YOLO26n-seg trained on the public Ultralytics crack-seg dataset
     (4,029 images) for 300 epochs. Training curves: results.csv / results.png.
  2. Fine-tuned for 20 epochs on the same dataset plus 50 crack-free photos of
     the underpass wall (empty label files), to stop the wall's joint pattern
     being flagged as cracks. Training curves: results_1.csv / results_1.png.
The result of stage 2 is best_v2.pt, used by generate_condition_report.py.
"""
from ultralytics import YOLO

# Stage 1: train on the public crack dataset
model = YOLO("yolo26n-seg.pt")
model.train(data="crack-seg.yaml", epochs=300, imgsz=640)

# Stage 2: fine-tune with the 50 crack-free site photos added as negatives.
# The dataset file below lists crack-seg plus the folder of site photos.
model = YOLO("runs/segment/train/weights/best.pt")
model.train(data="crack-seg-site.yaml", epochs=20, imgsz=640)
