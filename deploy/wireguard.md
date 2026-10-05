# WireGuard giữa Hostinger và VPS AI (khuyến nghị)

> ⚠️ Chỉ áp dụng khi VPS AI là máy ảo thật có systemd + root. Máy hiện tại là
> container thuê GPU (PID 1 = sshd, không systemd) nên KHÔNG dùng được —
> thay bằng `deploy/vps-ai/tunnel.sh` (SSH tunnel ngược).

Mục tiêu: Hostinger gọi VPS AI qua mạng riêng `10.10.0.x`, không phơi cổng 8000 ra
Internet. Ollama vẫn bind `127.0.0.1:11434`; proxy `ai-api` bind lên IP WireGuard.

| Máy | IP WireGuard | IP công khai |
|---|---|---|
| Hostinger | `10.10.0.1` | `187.127.208.218` |
| VPS AI | `10.10.0.2` | `103.9.158.134` |

## Cài đặt (cả hai máy)

```bash
sudo apt update && sudo apt install wireguard -y
cd /etc/wireguard
umask 077
wg genkey | tee privatekey | wg pubkey > publickey
cat publickey   # ghi lại để trao đổi giữa 2 máy
```

## Cấu hình VPS AI — `/etc/wireguard/wg0.conf`

```ini
[Interface]
Address = 10.10.0.2/24
ListenPort = 51820
PrivateKey = <VPS_AI_PRIVATEKEY>

[Peer]
PublicKey = <HOSTINGER_PUBLICKEY>
AllowedIPs = 10.10.0.1/32
```

## Cấu hình Hostinger — `/etc/wireguard/wg0.conf`

```ini
[Interface]
Address = 10.10.0.1/24
PrivateKey = <HOSTINGER_PRIVATEKEY>

[Peer]
PublicKey = <VPS_AI_PUBLICKEY>
Endpoint = 103.9.158.134:51820
AllowedIPs = 10.10.0.2/32
PersistentKeepalive = 25
```

## Bật + mở firewall

```bash
# VPS AI
sudo systemctl enable --now wg-quick@wg0
sudo ufw allow 51820/udp

# Hostinger
sudo systemctl enable --now wg-quick@wg0
```

## Kiểm tra

```bash
# Từ Hostinger
ping 10.10.0.2
curl http://10.10.0.2:8000/health
```

## Điều chỉnh khi dùng WireGuard

- Trên VPS AI: sửa `ai-api.service` bind `--host 10.10.0.2` thay vì `0.0.0.0`.
- Trên Hostinger `.env`: `INFERENCE_SERVER_URL=http://10.10.0.2:8000`,
  `OCR_SERVER_URL=http://10.10.0.2:8000`.
- Không cần `ufw allow from ... to port 8000` nữa (đã đi qua tunnel).
