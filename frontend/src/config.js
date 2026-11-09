// Cờ dữ liệu giả (WP-04 §3, prompt agent).
// - MOCK.all: toàn bộ API + WebSocket giả, chạy không cần backend: `npm run dev:mock`.
// - MOCK.diagnoses: chỉ phần ảnh/chẩn đoán (WP-07 chưa có). Khi backend xong WP-07, đặt false.
const env = import.meta.env || {}

export const MOCK = {
  all: env.MODE === 'mock',
  diagnoses: true,
}

export const API_BASE = '/api/v1'
export const WS_PATH = '/ws'
