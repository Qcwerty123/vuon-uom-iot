-- V002: lưu từng lá do AI tách (MobileSAM + ConvNeXt) để web vẽ viền/polygon từng lá.
-- Dạng: [{"tile":[r,c], "label":"SPOT", "conf":0.87, "bbox":[x,y,w,h] (pixel ảnh gốc),
--         "polygon":[[x,y],...] (chuẩn hóa 0..1 theo vùng crop_box)}]
-- Chẩn đoán cũ (mô hình trước) để NULL. Chạy lại nhiều lần không sao (IF NOT EXISTS).
ALTER TABLE diagnoses ADD COLUMN IF NOT EXISTS leaves JSONB;
