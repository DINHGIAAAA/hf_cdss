# Citation validation

## Vai trò

Module này **không** sinh khuyến cáo và **không** thay bước tìm tài liệu chính của hệ thống.

Sau khi đã có khuyến cáo + các đoạn tài liệu kèm theo (và có thể bổ sung thêm đoạn từ kho), nó trả lời:

> Từng mục khuyến cáo / ràng buộc / cảnh báo có được đoạn tài liệu hỗ trợ không?

Kết quả dùng để:

- Gắn mức chứng cứ: mạnh / yếu / thiếu (tách riêng khuyến cáo chính và phần an toàn).
- Cảnh báo trong bước kiểm chứng.
- Gắn link / đoạn nguồn cho giao diện.
- Khi khuyến cáo chính thiếu chứng cứ: hạ mức chắc chắn (`review`) và thêm cảnh báo rõ ràng.

---

## Đã cải thiện (trước đây là phần chưa hoàn thiện)

1. **Bổ sung đoạn từ kho** khi kiểm từng mục (theo mã nguồn / từ khóa / ưu tiên loại tài liệu), không chỉ túi đoạn đã kéo sẵn.
2. **Đồng nghĩa thuốc / nhóm thuốc** lấy từ danh mục nhóm điều trị và danh sách tên thuốc trong hệ thống (ví dụ ARNI ↔ sacubitril/valsartan).
3. **Từ khóa nhóm thuốc** mở rộng từ danh mục đó, không chỉ bốn trụ cột cứng.
4. **Mã nguồn nội bộ** được dùng để tìm lại đoạn trong kho (tên tài liệu / từ trong mã).
5. **Một lần tính** với đủ hồ sơ bệnh nhân; agent cảnh báo và kết quả cuối dùng chung bản đó.
6. **Status tổng** theo khuyến cáo chính; thiếu chứng cứ ở cảnh báo phụ chỉ làm “yếu”, không biến cả ca thành “thiếu”.
7. **Hạ mức khuyến cáo** khi thiếu chứng cứ (`apply_citation_guardrails`: status → `review` + cảnh báo giải thích).
8. **Cảnh báo liều / tương tác** ưu tiên đoạn nhãn thuốc.
9. **Giải thích** từng mục: từ cần có, từ đã khớp, từ còn thiếu (`required_terms` / `matched_terms` / `unmatched_terms` / `explanation`).

---

## Input / output

| | |
|--|--|
| **Input** | Khuyến cáo, ngữ cảnh đoạn tài liệu, hồ sơ bệnh nhân (tuỳ chọn) |
| **Output** | `CitationValidation` (status, recommendation_status, safety_status, supports[]) |
| **API** | Qua bước kiểm chứng (`/graphrag/verify`), không có endpoint riêng |

File chính: `service.py`, `terms.py`, `hydrate.py`, `links.py`.

---

## Ranh giới với phần khác

| Phần | Việc của họ | Việc không của citation_validation |
|------|-------------|-------------------------------------|
| Sinh khuyến cáo | Tạo danh sách thuốc / cảnh báo | — |
| Tìm tài liệu chính | Chọn đoạn ban đầu cho ca | — |
| Citation validation | Kiểm + bổ sung đoạn liên quan + chấm mạnh/yếu | Sinh rule lâm sàng |
| Gắn nguồn lên UI | Ưu tiên đoạn đã cite | Tính mức chứng cứ |

---

## Kiểm tra

```powershell
$env:PYTHONPATH=".;backend"
python -m pytest backend/app/tests/test_citation_validation.py -q
```
