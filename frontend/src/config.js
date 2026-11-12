// Cờ dữ liệu giả (WP-04 §3, prompt agent).
// - MOCK.all: toàn bộ API + WebSocket giả, chạy không cần backend: `npm run dev:mock`.
// - MOCK.diagnoses: chỉ phần ảnh/chẩn đoán. WP-07 đã có API thật nên đặt false.
const env = import.meta.env || {}

export const MOCK = {
  all: env.MODE === 'mock',
  diagnoses: false, // WP-07: backend đã có API chẩn đoán
}

export const API_BASE = '/api/v1'
export const WS_PATH = '/ws'
