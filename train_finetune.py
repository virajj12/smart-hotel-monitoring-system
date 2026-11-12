"""
Smart Hotel Monitoring System - YOLOv8 Fine-Tuning Pipeline
Supports training on Roboflow datasets (direct download or local YOLOv8 format).
Preserves existing model weights, provides class verification, and generates validation benchmarks.
"""

import os
import sys
import shutil
import argparse
from datetime import datetime
from pathlib import Path
import yaml
from ultralytics import YOLO

# Standard classes for the Smart Hotel Monitoring System
HOTEL_CLASSES = ["cockroach", "lizard", "rat", "no_apron", "no_gloves", "no_hairnet"]


def check_and_prepare_dataset(data_yaml_path: str) -> dict:
    """Validate data.yaml structure and class definitions."""
    if not os.path.exists(data_yaml_path):
        raise FileNotFoundError(f"data.yaml not found at: {data_yaml_path}")

    with open(data_yaml_path, "r", encoding="utf-8") as f:
        data_cfg = yaml.safe_load(f)

    names = data_cfg.get("names", [])
    if isinstance(names, dict):
        class_list = [names[k] for k in sorted(names.keys())]
    else:
        class_list = list(names)

    print("\n🔍 Dataset Class Inspection:")
    print(f"   Classes found ({len(class_list)}): {class_list}")
    print(f"   Target hotel classes ({len(HOTEL_CLASSES)}): {HOTEL_CLASSES}")

    # Check for missing classes / potential catastrophic forgetting
    missing = [c for c in HOTEL_CLASSES if c not in class_list]
    if missing:
        print(f"\n⚠️  WARNING: The dataset is missing classes: {missing}")
        print("   If you fine-tune exclusively on a PPE dataset without pest data,")
        print("   the model will suffer from catastrophic forgetting and lose pest detection capability.")
        print("   💡 RECOMMENDATION: Merge your PPE dataset with kitchen pest images before training.\n")

    return data_cfg


def download_from_roboflow(api_key: str, workspace: str, project_name: str, version: int) -> str:
    """Download dataset directly from Roboflow using the roboflow Python SDK."""
    try:
        from roboflow import Roboflow
    except ImportError:
        print("❌ 'roboflow' package not installed. Installing now...")
        os.system(f"{sys.executable} -m pip install roboflow")
        from roboflow import Roboflow

    print(f"\n📦 Fetching project '{workspace}/{project_name}' v{version} from Roboflow...")
    rf = Roboflow(api_key=api_key)
    project = rf.workspace(workspace).project(project_name)
    dataset = project.version(version).download("yolov8")

    data_yaml = os.path.join(dataset.location, "data.yaml")
    print(f"✅ Roboflow dataset downloaded to: {dataset.location}")
    return data_yaml


def train_model(
    data_yaml: str,
    base_model: str = "best.pt",
    epochs: int = 50,
    batch_size: int = 16,
    imgsz: int = 640,
    device: str = "",
    freeze_backbone: int = 0,
    auto_deploy: bool = False,
):
    """Fine-tune YOLOv8 model with transfer learning."""
    print("=" * 60)
    print("🚀 Starting YOLOv8 Hotel PPE / Hygiene Fine-Tuning")
    print("=" * 60)
    print(f"  • Base Model:       {base_model}")
    print(f"  • Dataset Config:   {data_yaml}")
    print(f"  • Epochs:           {epochs}")
    print(f"  • Batch Size:       {batch_size}")
    print(f"  • Image Size:       {imgsz}")
    print(f"  • Frozen Layers:    {freeze_backbone}")
    print("=" * 60)

    # 1. Load model
    if not os.path.exists(base_model):
        print(f"⚠️ {base_model} not found locally. Falling back to official 'yolov8n.pt' or 'yolov8s.pt'...")
        base_model = "yolov8s.pt"

    model = YOLO(base_model)

    # 2. Train with transfer learning
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_name = f"hotel_ppe_{timestamp}"

    train_args = {
        "data": data_yaml,
        "epochs": epochs,
        "batch": batch_size,
        "imgsz": imgsz,
        "project": "runs/detect",
        "name": run_name,
        "save": True,
        "pretrained": True,
        "patience": 15,       # Early stopping if no improvement for 15 epochs
        "verbose": True,
    }

    if device:
        train_args["device"] = device
    if freeze_backbone > 0:
        train_args["freeze"] = freeze_backbone

    results = model.train(**train_args)

    # 3. Evaluate on validation set
    print("\n📊 Running Validation Benchmarks...")
    val_results = model.val()
    print(f"  • Precision:  {val_results.results_dict.get('metrics/precision(B)', 0):.3f}")
    print(f"  • Recall:     {val_results.results_dict.get('metrics/recall(B)', 0):.3f}")
    print(f"  • mAP@50:     {val_results.results_dict.get('metrics/mAP50(B)', 0):.3f}")
    print(f"  • mAP@50-95:  {val_results.results_dict.get('metrics/mAP50-95(B)', 0):.3f}")

    # 4. Deployment
    best_weights = os.path.join("runs", "detect", run_name, "weights", "best.pt")
    if os.path.exists(best_weights):
        print(f"\n🎉 Best trained weights generated at: {best_weights}")
        if auto_deploy:
            # Create timestamped backup of current best.pt
            if os.path.exists("best.pt"):
                backup_path = f"best.pt.backup_{timestamp}"
                shutil.copy("best.pt", backup_path)
                print(f"💾 Backed up previous weights to: {backup_path}")

            shutil.copy(best_weights, "best.pt")
            print("🚀 Successfully deployed new weights to 'best.pt'!")
            print("   The monitoring system will now use your fine-tuned model.")
        else:
            print(f"💡 To activate these weights, run:")
            print(f"   copy \"{best_weights}\" best.pt")

    return results


def main():
    parser = argparse.ArgumentParser(description="Fine-tune YOLOv8 for Smart Hotel Monitoring")
    parser.add_argument("--data", type=str, default="", help="Path to local dataset data.yaml")
    parser.add_argument("--model", type=str, default="best.pt", help="Base model weights (default: best.pt or yolov8s.pt)")
    parser.add_argument("--epochs", type=int, default=50, help="Number of training epochs (default: 50)")
    parser.add_argument("--batch", type=int, default=16, help="Batch size (default: 16)")
    parser.add_argument("--imgsz", type=int, default=640, help="Inference image resolution (default: 640)")
    parser.add_argument("--device", type=str, default="", help="Device: '0' for CUDA GPU, 'cpu' for CPU")
    parser.add_argument("--freeze", type=int, default=0, help="Number of backbone layers to freeze")
    parser.add_argument("--deploy", action="store_true", help="Auto-deploy best.pt after training")

    # Roboflow automated download options
    parser.add_argument("--rf-key", type=str, default="", help="Roboflow API Key")
    parser.add_argument("--rf-workspace", type=str, default="", help="Roboflow workspace name")
    parser.add_argument("--rf-project", type=str, default="", help="Roboflow project name")
    parser.add_argument("--rf-version", type=int, default=1, help="Roboflow dataset version number")

    args = parser.parse_args()

    data_yaml_path = args.data

    # Download from Roboflow if credentials provided
    if args.rf_key and args.rf_workspace and args.rf_project:
        data_yaml_path = download_from_roboflow(
            api_key=args.rf_key,
            workspace=args.rf_workspace,
            project_name=args.rf_project,
            version=args.rf_version,
        )

    if not data_yaml_path:
        print("❌ Error: No dataset provided.")
        print("\nUsage Options:")
        print("  1. Local Dataset:")
        print("     python train_finetune.py --data path/to/dataset/data.yaml --epochs 50 --deploy")
        print("\n  2. Direct Roboflow Download:")
        print("     python train_finetune.py --rf-key YOUR_KEY --rf-workspace YOUR_WS --rf-project YOUR_PROJ --rf-version 1 --deploy")
        return

    check_and_prepare_dataset(data_yaml_path)

    train_model(
        data_yaml=data_yaml_path,
        base_model=args.model,
        epochs=args.epochs,
        batch_size=args.batch,
        imgsz=args.imgsz,
        device=args.device,
        freeze_backbone=args.freeze,
        auto_deploy=args.deploy,
    )


if __name__ == "__main__":
    main()

