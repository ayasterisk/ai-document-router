# Triển khai SoNNMT Document Router — 2 máy

Backend thật của hệ thống là `app.main:app` trong repo này (KHÔNG phải proxy `/api/chat`
trong `doc/SoNNMT/lo_trinh_trien_khai_ai_hostinger_ollama.md` — tài liệu đó là bản khái niệm
cũ, đã được thay bằng backend hoàn chỉnh).

## Phân vai máy (theo thực tế đã xác nhận)

| Vai trò | Máy | IP | User | Bản chất |
|---|---|---|---|---|
| API Gateway + Backend | Hostinger KVM | `187.127.208.218` | `root` | VPS thật, có systemd |
| Inference | VPS AI | `103.9.158.134` | `admin` | **Container/K8s pod** (PID 1 = `sshd`), RTX A4000, KHÔNG systemd |

Trên VPS AI đã có sẵn: Ollama chạy ở `127.0.0.1:11434`, model `qwen3-vl:8b`
(Q4_K_M, 6.1 GB), Python 3.12, tmux. `OLLAMA_HOST` rỗng → Ollama chỉ bind loopback (đúng).

## Kiến trúc kết nối

Vì VPS AI là container (không systemd, không chắc mở được cổng ra Internet), dùng
**SSH tunnel ngược**: container chủ động nối ra Hostinger, đưa Ollama về loopback Hostinger.

```
Tampermonkey (HTTPS + X-API-Key)
   → api.hokinhdoanh.club (Nginx, TLS) trên Hostinger
   → 127.0.0.1:8000  (app.main:app trên Hostinger)
   → 127.0.0.1:11434 (tunnel ngược) ──────── SSH ────────► 127.0.0.1:11434 (Ollama)
                                                            qwen3-vl:8b (RTX A4000)
```

Không mở cổng nào của container ra Internet; không cần proxy; không cần Python trên container.

---

## Bước 0 — Xác nhận VPS AI (đã làm xong)

```bash
ollama list                                  # qwen3-vl:8b (6.1 GB)
curl -s http://127.0.0.1:11434/api/tags      # trả JSON => Ollama đang serve
echo "OLLAMA_HOST=[$OLLAMA_HOST]"            # [] => chỉ bind loopback
nvidia-smi                                   # RTX A4000 16GB
```

## Bước 1 — Mở tunnel ngược (trên container VPS AI)

```bash
ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519
ssh-copy-id root@187.127.208.218              # nhập mật khẩu root Hostinger 1 lần
ssh -o StrictHostKeyChecking=accept-new root@187.127.208.218 'echo OK'

tmux new -s tunnel
bash tunnel.sh                                # file deploy/vps-ai/tunnel.sh
# tách khỏi tmux: Ctrl+B rồi nhấn D
```

## Bước 2 — Kiểm tra tunnel (trên Hostinger)

```bash
ssh root@187.127.208.218
curl -s http://127.0.0.1:11434/api/tags | head -c 300
```

Ra JSON danh sách model → thông. Nếu không, kiểm tra `tmux attach -t tunnel` trên container.

## Bước 3 — Triển khai backend lên Hostinger (VPS thật, có systemd)

```bash
ssh root@187.127.208.218
apt update && apt install -y nginx python3 python3-venv git

# Cách 1: git clone (nếu repo đã đẩy lên remote)
git clone <REPO_URL> /opt/document-ai
# Cách 2: scp từ máy dev — chỉ cần app/, requirements.lock.txt, .env
#   scp -r app requirements.lock.txt root@187.127.208.218:/opt/document-ai/

cd /opt/document-ai
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.lock.txt     # không cần Poppler; raster dùng PDFium
```

> Ubuntu 26.04 có thể ship Python 3.14. Nếu `pip install` không build được wheel
> (pydantic-core, pypdfium2…), dùng `uv`/pyenv cài Python 3.12 — repo đã kiểm thử trên 3.12.

Tạo `.env` từ `deploy/hostinger/.env.example` (điền token thật, sửa domain/origin):

```bash
source venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
# cửa sổ khác:
curl http://127.0.0.1:8000/health
```

## Bước 4 — Nginx + systemd trên Hostinger

```bash
# Copy deploy/hostinger/nginx.conf → /etc/nginx/sites-available/document-ai
ln -s /etc/nginx/sites-available/document-ai /etc/nginx/sites-enabled/document-ai
nginx -t && systemctl restart nginx

# Copy deploy/hostinger/document-ai.service → /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now document-ai
systemctl status document-ai --no-pager
```

## Bước 5 — Domain + HTTPS

1. DNS record `A`: `api` → `187.127.208.218` (thay `api.hokinhdoanh.club` bằng domain thật).
2. `nslookup api.hokinhdoanh.club` phải ra IP Hostinger.
3. `apt install certbot python3-certbot-nginx -y`
4. `certbot --nginx -d api.hokinhdoanh.club`

## Bước 6 — Kiểm tra end-to-end

```bash
# /ready phải báo inference_configured=true
curl https://api.hokinhdoanh.club/ready -H "X-API-Key: <ROUTER_TOKEN>"

# Gửi 1 văn bản
curl -X POST https://api.hokinhdoanh.club/v1/jobs \
  -H "X-API-Key: <ROUTER_TOKEN>" -H "Idempotency-Key: test-1" \
  -F "document_id=TEST1" -F "received_on=2026-09-08" \
  -F "text=CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM ..."
```

Request đầu tiên sẽ chậm vài chục giây vì Ollama nạp model vào VRAM (6.1 GB).

---

## Duy trì & lưu ý vận hành

- **Pod restart** (nhà cung cấp tự stop pod rảnh, hoặc bạn stop/start): sshd tự lên nhưng
  tunnel + Ollama có thể tắt. Sau mỗi lần restart cần:
  1. Kiểm tra `curl -s http://127.0.0.1:11434/api/tags`; nếu lỗi thì khởi động lại `ollama serve`.
  2. Chạy lại tunnel: `tmux new -s tunnel && bash tunnel.sh`.
- **`ai-api.service` / `wireguard.md`** chỉ dùng khi VPS AI là VPS thật có systemd — không áp
  dụng cho container hiện tại.
- **Model chỉ nạp khi có request** (Ollama unload sau vài phút rảnh) → request đầu luôn chậm hơn.

## Những điểm khác với tài liệu cũ

1. **Không có endpoint `/api/chat`.** Client gọi `/v1/jobs` (async) hoặc `/classify`
   (đồng bộ), xác thực bằng `X-API-Key`.
2. **Ollama nói OpenAI-compat** `/v1/chat/completions` — backend đã gọi đúng endpoint này.
3. **`OCR_MODEL` phải là tag Ollama** `qwen3-vl:8b` (không phải `Qwen/Qwen2.5-VL-7B-Instruct`).
4. **Rate limit chưa có ở tầng backend** (chỉ giới hạn queue/upload). Nếu cần `10 req/phút/user`,
   thêm `limit_req` ở Nginx hoặc middleware riêng.
5. **Mọi kết quả model đều `requires_confirmation=true`** — con người vẫn phải duyệt; đây là
   chính sách cố ý của repo.

## Việc cần điền trước khi chạy

- Domain/subdomain thật (mặc định dùng `api.hokinhdoanh.club`).
- Origin thật của website Sở → `ROUTER_ALLOWED_ORIGINS`.
- Token `ROUTER_API_KEYS` (sinh bằng `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`).
