# 📁 Cách Tổ Chức Repository Để Đưa Lên HACS

Đây là hướng dẫn cấu trúc thư mục **chính xác** bạn cần tạo trên GitHub.

## Cấu Trúc Thư Mục

```
ha-optimizer/                          ← tên repo GitHub của bạn
│
├── custom_components/
│   └── ha_optimizer/                  ← toàn bộ code integration
│       ├── __init__.py
│       ├── const.py
│       ├── config_flow.py
│       ├── scanner.py
│       ├── purge_engine.py
│       ├── store.py
│       ├── fingerprint.py
│       ├── manifest.json
│       ├── services.yaml
│       ├── strings.json
│       └── panel.html
│
├── .github/
│   ├── workflows/
│   │   └── validate.yml               ← CI: HACS + hassfest validation
│   └── ISSUE_TEMPLATE/
│       ├── bug_report.yml
│       └── feature_request.yml
│
├── README.md                          ← tiếng Anh (bắt buộc)
├── README_vi.md                       ← tiếng Việt
├── info.md                            ← hiển thị trong HACS store
├── hacs.json                          ← metadata HACS (BẮT BUỘC)
├── CHANGELOG.md
├── LICENSE                            ← BẮT BUỘC để HACS chấp nhận
└── .gitignore
```

---

## Các Bước Đưa Lên GitHub

### 1. Tạo repo mới trên GitHub
- Tên repo: `ha-optimizer` (hoặc tuỳ bạn)
- Visibility: **Public** (HACS yêu cầu public)
- **KHÔNG** tick "Add README" (bạn đã có sẵn)

### 2. Push code lên
```bash
git init
git add .
git commit -m "feat: initial release v1.0.0"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/ha-optimizer.git
git push -u origin main
```

### 3. Tạo Release đầu tiên
- Vào tab **Releases** → **Create a new release**
- Tag: `v1.0.0`
- Title: `v1.0.0 — Initial Release`
- Nhấn **Publish release**

> ⚠️ HACS **bắt buộc** phải có ít nhất một Release với tag dạng `vX.Y.Z`

### 4. Cập nhật manifest.json
Đảm bảo `version` trong `custom_components/ha_optimizer/manifest.json` khớp với tag release:
```json
{
  "version": "1.0.0"
}
```

### 5. Thêm vào HACS
Người dùng thêm bằng cách:
1. HACS → Integrations → menu ⋮ → **Custom repositories**
2. URL: `https://github.com/YOUR_USERNAME/ha-optimizer`
3. Category: **Integration**

---

## Checklist HACS Validation

Trước khi submit, đảm bảo tất cả điều này đúng:

- [x] `hacs.json` tồn tại ở root repo
- [x] `LICENSE` tồn tại ở root repo  
- [x] `README.md` tồn tại ở root repo
- [x] `custom_components/ha_optimizer/manifest.json` có đủ các field bắt buộc
- [x] `manifest.json` có `"version"` khớp với GitHub release tag
- [x] `manifest.json` có `"domain": "ha_optimizer"`
- [x] Repo là **Public**
- [x] Có ít nhất 1 Release với tag `vX.Y.Z`
- [x] GitHub Actions `validate.yml` pass (HACS action + hassfest)

---

## Sau Khi Release Mới

Khi bạn cập nhật code và muốn release phiên bản mới:

```bash
# 1. Cập nhật version trong manifest.json
# 2. Cập nhật CHANGELOG.md
git add .
git commit -m "feat: v1.1.0 — mô tả thay đổi"
git push

# 3. Tạo tag mới
git tag v1.1.0
git push origin v1.1.0
```

GitHub Actions sẽ tự động:
- Validate HACS + hassfest
- Tạo Release với file `ha_optimizer.zip`
