#!/usr/bin/env bash
# Xoá các file/thư mục nhạy cảm khỏi TOÀN BỘ lịch sử git (không chỉ commit mới nhất).
#
# CẢNH BÁO — hành động này viết lại lịch sử git (thay đổi hash mọi commit):
#   - Mọi người đang clone repo phải clone lại từ đầu sau khi bạn force-push.
#   - Không thể hoàn tác trừ khi bạn có backup (script tự tạo backup bên dưới).
#   - Nếu repo đã public, coi các file này là ĐÃ RÒ RỈ (đã có thể bị người khác
#     tải/cache/fork trước khi bạn dọn) — cần đánh giá rủi ro thực tế, không chỉ
#     xoá khỏi git là xong.
#
# Cách dùng:
#   1. Sửa mảng PATHS_TO_REMOVE bên dưới cho đúng danh sách bạn muốn xoá.
#   2. chmod +x tools/purge_sensitive_history.sh
#   3. ./tools/purge_sensitive_history.sh
#   4. Kiểm tra lại repo (xem phần "Sau khi chạy" ở cuối file).
#   5. git push --force --all && git push --force --tags
#   6. Báo mọi cộng tác viên clone lại repo mới, không pull vào repo cũ.
#
# Yêu cầu: chạy trong thư mục gốc của repo (nơi có .git), Python3 + pip có mạng
# để cài git-filter-repo nếu chưa có.

set -euo pipefail

# --------------------------------------------------------------------------
# 1) Danh sách đường dẫn cần xoá khỏi lịch sử — SỬA THEO NHU CẦU TRƯỚC KHI CHẠY
# --------------------------------------------------------------------------
PATHS_TO_REMOVE=(
  "doc/SoNNMT"
  "doc/SoTC"
  "doc/SoYT"
  "output"
  "tmp"
  # Bỏ comment nếu các file này cũng chứa nội dung nội bộ/nhạy cảm:
  # "Bao-cao-thiet-ke-Server-AI-Phan-loai-Dinh-tuyen-Van-ban-den.pdf"
  # "ke-hoach-trien-khai-SoNNMT.docx"
  # "ke-hoach-trien-khai-SoNNMT.pdf"
)

# --------------------------------------------------------------------------
# 2) Kiểm tra điều kiện
# --------------------------------------------------------------------------
if [ ! -d ".git" ]; then
  echo "Lỗi: phải chạy script này từ thư mục gốc của repo (nơi có .git)." >&2
  exit 1
fi

if [ -n "$(git status --porcelain)" ]; then
  echo "Lỗi: working tree có thay đổi chưa commit. Hãy commit hoặc stash trước." >&2
  exit 1
fi

if ! command -v git-filter-repo >/dev/null 2>&1; then
  echo "git-filter-repo chưa có, đang cài (pip install --user git-filter-repo)..."
  pip install --user git-filter-repo
  export PATH="$HOME/.local/bin:$PATH"
  if ! command -v git-filter-repo >/dev/null 2>&1; then
    echo "Lỗi: cài xong nhưng vẫn không thấy lệnh git-filter-repo trong PATH." >&2
    echo "Thử: python3 -m pip install --user git-filter-repo rồi mở terminal mới." >&2
    exit 1
  fi
fi

# --------------------------------------------------------------------------
# 3) Backup toàn bộ repo trước khi viết lại lịch sử
# --------------------------------------------------------------------------
REPO_DIR="$(pwd)"
REPO_NAME="$(basename "$REPO_DIR")"
BACKUP_DIR="../${REPO_NAME}-backup-$(date +%Y%m%d-%H%M%S)"
echo "Đang backup repo hiện tại (bao gồm lịch sử cũ) vào: $BACKUP_DIR"
cp -a "$REPO_DIR" "$BACKUP_DIR"
echo "Backup xong. Nếu có sự cố, khôi phục bằng cách dùng lại thư mục đó."

# --------------------------------------------------------------------------
# 4) Chạy git-filter-repo để xoá các path khỏi mọi commit
# --------------------------------------------------------------------------
ARGS=()
for p in "${PATHS_TO_REMOVE[@]}"; do
  ARGS+=(--path "$p" --invert-paths)
done

echo "Đang xoá khỏi lịch sử: ${PATHS_TO_REMOVE[*]}"
git filter-repo --force "${ARGS[@]}"

# git-filter-repo tự xoá remote 'origin' để tránh push nhầm lên bản gốc lịch sử cũ.
# Gắn lại remote nếu bạn biết chắc muốn force-push lên cùng remote đó.
if [ -n "${GIT_REMOTE_URL:-}" ]; then
  git remote add origin "$GIT_REMOTE_URL"
  echo "Đã gắn lại remote origin -> $GIT_REMOTE_URL"
else
  echo "Chưa gắn lại remote origin. Gắn thủ công bằng:"
  echo "  git remote add origin <url-repo-cua-ban>"
fi

# --------------------------------------------------------------------------
# 5) Dọn thêm reflog + gc để giảm kích thước .git thực sự
# --------------------------------------------------------------------------
git reflog expire --expire=now --all
git gc --prune=now --aggressive

echo
echo "=== Xong bước xoá lịch sử cục bộ ==="
echo "Kích thước .git bây giờ:"
du -sh .git

cat <<'EOF'

Sau khi chạy:
  1. Kiểm tra lại bằng: git log --oneline --stat | grep -i "<ten-file-nhay-cam>"
     (không nên còn thấy các path đã xoá xuất hiện ở bất kỳ commit nào)
  2. Cập nhật .gitignore để các path này không bị commit lại lần nữa.
  3. Force-push (GHI ĐÈ lịch sử trên remote — chỉ làm khi chắc chắn):
       git push --force --all
       git push --force --tags
  4. Vào GitHub -> Settings -> tùy chọn "purge cache"/liên hệ GitHub Support
     nếu repo từng public, vì GitHub có thể cache commit cũ; đồng thời kiểm tra
     có fork nào của repo đang tồn tại không (các fork vẫn giữ lịch sử cũ).
  5. Đổi mọi API key/token/secret từng nằm trong các file đã xoá (nếu có) —
     xoá khỏi git không có nghĩa là khoá đã từng lộ trở nên an toàn trở lại.
  6. Báo tất cả cộng tác viên: xoá bản clone cũ, clone lại từ đầu. Không "git pull".
EOF
