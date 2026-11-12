"""Tạo leaf.onnx GIẢ (ConvNeXt-Tiny khởi tạo ngẫu nhiên, 4 lớp) để thử luồng khi chưa có mô hình thật.

Dùng:  python scripts/make_dummy_model.py <thư_mục_đích>
CẢNH BÁO: nhãn của mô hình giả là NGẪU NHIÊN, KHÔNG được dùng cho demo hay báo cáo.
Không ghi đè leaf.onnx đã có.
"""
import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    out_dir = Path(sys.argv[1])
    dst = out_dir / "leaf.onnx"
    if dst.exists():
        print(f"DỪNG: {dst} đã tồn tại, không ghi đè (có thể là mô hình thật). Chọn thư mục khác.")
        return 1
    import timm
    import torch

    out_dir.mkdir(parents=True, exist_ok=True)
    model = timm.create_model("convnext_tiny", pretrained=False, num_classes=4).eval()
    torch.onnx.export(model, torch.zeros(1, 3, 224, 224), str(dst), input_names=["input"], output_names=["logits"],
                      dynamic_axes={"input": {0: "batch"}, "logits": {0: "batch"}}, opset_version=17, dynamo=False)
    meta = out_dir / "model_meta.json"
    if not meta.exists():
        meta.write_text(json.dumps({"classes": ["HEALTHY", "SPOT", "YELLOW", "PEST"], "dummy": True}), encoding="utf-8")
    print("=" * 70)
    print(f"Đã tạo {dst}")
    print("CẢNH BÁO: ĐÂY LÀ MÔ HÌNH GIẢ, nhãn NGẪU NHIÊN. KHÔNG dùng cho demo/báo cáo.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
