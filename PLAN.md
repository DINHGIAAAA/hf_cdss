# Plan: Xác minh & vá "follow-up loop" trong chatbot

## Context

Người dùng đã đối chiếu code và kết luận **~70% hạ tầng đã có**, chỉ thiếu
phần "wiring" cuối. Đề xuất gồm 5 mảng:

1. Thêm intent `"follow_up_detail"` vào `INTENT_PATTERNS`
2. Thêm helper `_last_assistant_message()`
3. Mở rộng `aggregate_conversation_context` để nhận `last_assistant_message`
4. Cập nhật prompt `explanation.py` thêm rule cho `follow_up_detail`
5. Caching embedding theo `message_id` để tránh O(n²)

Sau khi đọc kỹ code thật (git status cũng cho thấy các file liên quan đã được
sửa gần đây), kết luận thực tế khác với phân tích trên:

| Đề xuất | Trạng thái thực tế trong code |
|---|---|
| 1. Thêm `follow_up_detail` intent | **Đã có** — `clinical_state.py:27-41` (đã gated bằng `has_prior_assistant`) |
| 2. Helper `_last_assistant_message` | **Đã có** — `service.py:534-538` |
| 3. Mở rộng `aggregate_conversation_context` nhận `last_assistant_message` | **Đã có** — `semantic.py:186, 202-210, 220, 239, 244`; `_with_previous_answer` đã gắn header `[Your previous answer]` và excerpt tối đa 4000 ký tự |
| 4. Cập nhật prompt thêm rule follow-up | **Đã có** — `explanation.py:15-19` đã có block `=== FOLLOW-UP / DEEPEN (when clinical_state.intent is follow_up_detail) ===` yêu cầu *không đổi status*, *không lặp checklist*, *đào sâu theo focus_class_ids* |
| 5. Cache embedding theo `message_id` | **Một nửa**: `embed_query` đã có `lru_cache(maxsize=256)` ở `semantic_retrieval/service.py:49-50`, nhưng `embed_documents` (dùng trong `aggregate_conversation_context`) **chưa cache** — đây đúng là điểm yếu O(n²) cần xử lý |

## Phát hiện quan trọng

**Wiring đã hoàn chỉnh** (`service.py:541-555`):

```python
def _conversation_context_for_llm(current_message, conversation_id, *, clinical_state=None):
    intent = (clinical_state or {}).get("intent")
    last_assistant = _last_assistant_message(conversation_id) if intent == "follow_up_detail" else None
    return aggregate_conversation_context(
        current_message,
        _prior_user_messages(conversation_id),
        last_assistant_message=last_assistant,
    )
```

`_conversation_context_for_llm` được gọi đúng ở cả 2 entry points
(`stream_chat` dòng 793, `process_chat` dòng 1005).

**Test đã tồn tại** (`tests/test_chat_follow_up_context.py`) đã verify đủ 3 trụ cột:
- Intent `follow_up_detail` chỉ được set khi `has_prior_assistant=True`
- `[Your previous answer]` được chèn vào context khi intent = follow_up
- `aggregate_conversation_context` xử lý `last_assistant_message` độc lập

**Vậy "loop chưa đúng ý" có thể do đâu?**

Hai nghi vấn cần xác minh trước khi viết patch mới:

1. **Cache embedding** — `aggregate_conversation_context` vẫn gọi
   `embed_documents(texts)` mỗi lượt với `[current, *prior]`. Khi prior list
   dài (cấu hình `clinical_intake_history_max_messages=12`), mỗi turn embed
   lại 13 câu. Đây là chi phí thực và đúng là vấn đề — `embed_documents`
   không có `lru_cache`.
2. **Reference resolution chưa có** — `aggregate_conversation_context` chỉ
   lấy excerpt assistant cuối + list prior user. Khi user hỏi
   "SGLT2i chi tiết hơn", hệ thống biết intent là `follow_up_detail` và có
   assistant text, nhưng **không tự tag được câu trả lời cũ đang nói về
   class nào** để LLM hiểu ngữ cảnh. Hiện đã có
   `focus_class_ids_from_message` ở `question_focus.py` chạy trên message
   mới, nhưng chưa có tương đương chạy trên assistant text cũ.

## Recommended Approach

Phạm vi sửa chữa thực sự cần làm rất gọn — **không viết lại những gì đã có**:

### Bước 1 — Cache embedding theo message text (rủi ro thấp, hiệu quả cao)

**File**: `backend/app/modules/semantic_retrieval/service.py`

Mở rộng `_embed_query_cached` (đã có `lru_cache(256)`) để phủ cả batch case.
Hai hướng đều khả thi:

- **Hướng A (an toàn, lazy)**: thêm `@lru_cache(maxsize=1024)` cho một helper
  `_embed_one(text)` rồi viết lại `embed_documents` để gọi `_embed_one` từng
  phần tử. Tận dụng cache key theo text — cùng câu hỏi lặp lại sẽ trúng cache.
  Cache key phụ thuộc `embedding_index_version()` nên model đổi sẽ tự miss.
- **Hướng B (mạnh hơn)**: cache theo `message_id` qua Redis. Ưu điểm: persist
  qua restart; nhược điểm: thêm 1 lớp I/O, cần TTL, và cần truyền
  `message_id` xuống `aggregate_conversation_context` (hiện chỉ nhận text).

→ **Chọn Hướng A** cho ponytail-mode (đã có sẵn pattern `lru_cache`, không
thêm dependency, không thêm I/O). Caching per-text là đủ vì:

- Trong 1 conversation, prior messages thường lặp lại gần giống nhau qua các turn
- `clinical_intake_history_max_messages=12` giới hạn tổng số text cần embed
- `lru_cache(1024)` đủ chứa nhiều conversation

### Bước 2 — Resolve "assistant context tag" cho `follow_up_detail`

**File**: `backend/app/modules/chat/clinical_state.py`

Không cần đổi `aggregate_conversation_context`. Chỉ cần gắn
`focus_medication_classes` từ assistant text cũ vào clinical_state khi
intent = `follow_up_detail`. Cụ thể trong `build_clinical_state`:

```python
# Khi has_prior_assistant, lấy last_assistant_message và merge focus
prior_focus: set[str] = set()
if has_prior_assistant:
    from app.modules.chat.service import _last_assistant_message  # circular, refactor nếu cần
    # Hoặc truyền last_assistant_message từ caller (service.py đã có sẵn).
    ...
```

Vì `service.py` đã có `_last_assistant_message(conversation_id)` và
`build_clinical_state` được gọi từ cả `stream_chat` (dòng 654) và
`process_chat` (dòng 888), cách sạch nhất là **truyền tham số** thay vì
import ngược:

- Thêm tham số `last_assistant_message: str | None = None` vào
  `build_clinical_state`
- Trong `service.py` chỗ gọi `build_clinical_state`, truyền
  `_last_assistant_message(conversation_id)` (đã được dùng ở dòng 657/891
  cho `has_prior_assistant`)
- Bên trong `build_clinical_state`, nếu `last_assistant_message` có nội
  dung thì gọi `focus_class_ids_from_message(last_assistant_message)` và
  union vào `focus_classes`

Điều này đảm bảo khi user hỏi "SGLT2i chi tiết hơn",
`focus_medication_classes` đã chứa `sglt2i` (từ message mới) **và** class
nào đó từ câu assistant trước → LLM hiểu ngữ cảnh đầy đủ mà không cần
prompt phức tạp hơn.

### Bước 3 — Test bổ sung

**File**: `backend/app/tests/test_chat_follow_up_context.py`

Thêm 2 case:

- Verify `focus_medication_classes` của state khi `has_prior_assistant=True`
  và assistant text nhắc "MRA" → state chứa `mra`.
- Verify cache hit: gọi `aggregate_conversation_context` 2 lần với cùng
  prior list → `embed_documents` cache hit tăng (kiểm tra qua
  `_embed_query_cached.cache_info()`).

## Critical Files

| File | Thay đổi |
|---|---|
| `backend/app/modules/semantic_retrieval/service.py` | Thêm helper cached cho `embed_documents` (Hướng A) |
| `backend/app/modules/chat/clinical_state.py` | Mở rộng `build_clinical_state` để include focus classes từ assistant text khi `has_prior_assistant` |
| `backend/app/modules/chat/service.py` | Truyền `last_assistant_message` vào `build_clinical_state` ở 2 call sites |
| `backend/app/tests/test_chat_follow_up_context.py` | Thêm 2 test cho focus resolution + cache hit |

**Không sửa**:

- `chat/service.py::_conversation_context_for_llm` — wiring đã đúng
- `clinical_intake_extraction/semantic.py` — `aggregate_conversation_context` đã nhận `last_assistant_message`
- `prompts/explanation.py` — prompt đã có rule `follow_up_detail`
- `chat/clinical_state.py::INTENT_PATTERNS` — đã có `follow_up_detail` với `has_prior_assistant` gate

## Verification

1. **Static check**:

   ```bash
   cd backend
   python -m pytest app/tests/test_chat_follow_up_context.py -v
   python -m pytest app/tests/test_explanation.py -v
   ```

   Cả 2 file test phải pass — bao gồm 3 test cũ + 2 test mới.

2. **Smoke test manual** qua `stream_chat`:

   - Turn 1: gửi "Co nen tang MRA hoac bat dau dapagliflozin?"
     → kiểm tra response có nhắc MRA + SGLT2i với status khác nhau.
   - Turn 2: gửi "SGLT2i chi tiet hon duoc khong?"
     → kiểm tra:
       - `clinical_state.intent == "follow_up_detail"`
       - `conversation_context` chứa `[Your previous answer]` với excerpt câu trả lời turn 1
       - `focus_medication_classes` chứa `sglt2i`
       - Answer không dump full checklist, không đổi status turn 1

3. **Performance**:

   - Đo `_embed_query_cached.cache_info()` sau 10 turn
     → `hits` phải tăng (cùng prior user messages được embed lặp lại).

## Skipped

- **Redis-based message-id cache (Hướng B)** — chỉ thêm khi `lru_cache`
  chứng minh không đủ (đo `cache_misses` ổn định > 30% qua trace thực).
- **Tăng cường reference resolution** (vd: tách từng class thành block
  riêng trong assistant excerpt) — đủ dùng với focus_classes gắn trong state.
- **Bổ sung intent `comparison_resolve`** (vd: "so sánh MRA với cái vừa nói")
  — YAGNI, `choice_question` đã cover.

---

# Plan: Multi-Question — Answer Q1 → Confirm → Execute Q2

## Context

Khi user hỏi multi-question (ví dụ: "MRA hay SGLT2i? Và có cần thêm ARNI không?"),
hệ thống hiện tại:
- Không split được câu hỏi — `_intent()` trả về 1 intent duy nhất
- Không có cơ chế "trả lời câu 1 trước, hỏi xác nhận trước khi tiếp"
- LLM nhận raw `user_input` chứa tất cả câu hỏi, trả lời tất cả một lượt

**Yêu cầu**: Answer Q1 → Confirm → Execute Q2 (→ Confirm → Execute Q3...)

## Architecture

```
[User multi-question message]
         ↓
[detect_multi_question(message)] → list[str] questions
         ↓
[Answer Q1] → status="multi_question_confirm"
         ↓
[User confirms: multi_question_action="continue"]
         ↓
[Answer Q2] → (more remaining?) → confirm or done
```

## Implementation (5 Files)

### Bước 1 — Split multi-question (`clinical_intake_extraction/semantic.py`)

Thêm function `detect_multi_question(message: str) -> list[str]`:

```python
def detect_multi_question(message: str) -> list[str]:
    """Split a multi-question message into individual questions.

    Returns [message] (single-item) to leave normal flow unchanged.
    """
    normalized = normalize_text(message)
    sentences = [s.strip() for s in normalized.split("?") if s.strip()]
    MIN_LEN = 15
    questions = [s for s in sentences if len(s) >= MIN_LEN]
    return questions if len(questions) > 1 else [message]
```

### Bước 2 — Schema extension (`schemas/chat.py`)

```python
class PendingMultiQuestion(BaseModel):
    conversation_id: str
    answered_qs: list[str]            # ["Q1 content", "Q2 content", ...]
    remaining_qs: list[str]           # ["Q3 content", ...]
    current_index: int                # 1 = answering Q2
    patient_snapshot: dict            # merged patient for replay
    clinical_state_snapshot: dict

class ChatRequest(BaseModel):
    multi_question_action: Literal["continue", "stop"] | None = None
    pending_multi_question: PendingMultiQuestion | None = None

class ChatResponse(BaseModel):
    # ... existing fields
    pending_multi_question: PendingMultiQuestion | None = None
```

### Bước 3 — Service wiring (`chat/service.py`)

**3a. Detect ở đầu mỗi entry point** (trước khi extract patient):

```python
def _is_multi_question(message: str) -> bool:
    from app.modules.clinical_intake_extraction.semantic import detect_multi_question
    return len(detect_multi_question(message)) > 1

# Trong stream_chat/process_chat, trước khi extract:
if _is_multi_question(request.message) and request.multi_question_action is None:
    questions = detect_multi_question(request.message)
    request = request.model_copy(update={"message": questions[0]})
    _pending_multi[conversation_id] = {
        "remaining": questions[1:],
        "answered": [questions[0]],
        "current_index": 1,
    }
```

**3b. Continue handler** (khi `multi_question_action == "continue"`):

```python
if request.multi_question_action == "continue" and request.pending_multi_question:
    pending = request.pending_multi_question
    next_q = pending.remaining_qs[0]
    remaining = pending.remaining_qs[1:]
    answered = pending.answered_qs + [next_q]
    # Override message để extraction/recommendation chạy trên next_q
    request = request.model_copy(update={"message": next_q})
    _pending_multi[conversation_id] = {
        "remaining": remaining,
        "answered": answered,
        "current_index": pending.current_index + 1,
    }
```

**3c. Confirmation response path** (sau khi có LLM answer):

Thay vì yield `status="completed"`, kiểm tra `_pending_multi[conversation_id]`:

```python
if pending := _pending_multi.get(conversation_id):
    next_q = pending["remaining"][0] if pending["remaining"] else None
    confirm_msg = _build_multi_question_confirm_message(
        pending["answered"][-1], next_q,
        next_q_index=len(pending["answered"]),
        language=request.language or "vi"
    )
    assistant_message = _message(conversation_id, "assistant", confirm_msg, {
        "status": "multi_question_confirm",
    })
    pending_multi[conversation_id] = {
        **pending,
        "llm_answer_snapshot": final_answer,
    }
    yield _sse("done", ChatResponse(
        status="multi_question_confirm",
        assistant_message=assistant_message,
        pending_multi_question=PendingMultiQuestion(...),
        ...
    ).model_dump(mode="json"))
    return
```

**3d. Build confirm message**:

```python
def _build_multi_question_confirm_message(
    current_q: str, next_q: str | None, *, next_q_index: int, language: str
) -> str:
    if language == "vi":
        msg = f"**Câu hỏi {next_q_index}:** {current_q}\n\nTôi đã trả lời câu hỏi trên."
        if next_q:
            msg += f"\n\n**Câu hỏi tiếp theo ({next_q_index + 1}):** {next_q}\n\n"
            msg += "Bạn có muốn tôi tiếp tục trả lời câu tiếp theo không?"
        else:
            msg += "\n\n_Đã trả lời tất cả câu hỏi._"
    else:
        msg = f"**Question {next_q_index}:** {current_q}\n\nI've answered this question."
        if next_q:
            msg += f"\n\n**Next question ({next_q_index + 1}):** {next_q}\n\n"
            msg += "Would you like me to continue?"
        else:
            msg += "\n\n_All questions have been answered._"
    return msg
```

### Bước 4 — Prompt update (`prompts/explanation.py`)

Thêm section `=== MULTI-QUESTION ===`:

```python
"=== MULTI-QUESTION ===\n"
"If user_input contains multiple distinct questions (separated by '?' or 'và'), "
"answer ONLY the first question. Do not attempt to answer all questions at once. "
"The system will ask for confirmation before proceeding to the next question.\n"
"Focus on the most clinically significant question first.\n\n"
```

### Bước 5 — Test (`tests/test_chat_follow_up_context.py`)

Thêm:

```python
def test_detect_multi_question_splits_correctly() -> None:
    from app.modules.clinical_intake_extraction.semantic import detect_multi_question
    qs = detect_multi_question("MRA hay SGLT2i? Co can them ARNI khong?")
    assert len(qs) == 2
    assert "MRA hay SGLT2i" in qs[0]
    assert "Co can them ARNI" in qs[1]

def test_detect_multi_question_single_returns_unchanged() -> None:
    from app.modules.clinical_intake_extraction.semantic import detect_multi_question
    qs = detect_multi_question("MRA hay SGLT2i?")
    assert len(qs) == 1
```

## Critical Files

| File | Thay đổi |
|---|---|
| `backend/app/modules/clinical_intake_extraction/semantic.py` | Thêm `detect_multi_question()` |
| `backend/app/schemas/chat.py` | Thêm `PendingMultiQuestion`, mở rộng `ChatRequest`/`ChatResponse` |
| `backend/app/modules/chat/service.py` | Detect multi-Q, confirmation flow, continue/stop handler |
| `backend/app/prompts/explanation.py` | Thêm prompt rule multi-question |
| `backend/app/tests/test_chat_follow_up_context.py` | Thêm 2 test cho `detect_multi_question` |

**Không sửa**:
- `clinical_state.py::INTENT_PATTERNS` — multi-question không cần intent riêng, xử lý ở service layer
- Frontend — client xử lý `status="multi_question_confirm"` riêng

## Verification

1. **Unit**: `detect_multi_question` splits correctly, single question unchanged
2. **Smoke test**: gửi multi-question → `status="multi_question_confirm"` → gửi continue → answer Q2
3. **Regression**: chạy lại `test_chat_follow_up_context.py` + `test_clinical_intake_semantic.py`

## Skipped

- **Frontend changes**: client xử lý `multi_question_confirm` status (backend cung cấp đúng response)
- **Reuse recommendation** qua các Q (nếu Q1 và Q2 cùng drug class) — chạy lại recommendation bình thường
- **Data sufficiency check trước confirm** — cứ trả lời Q1 rồi confirm, kiểm tra missing data ở Q2 nếu cần
- **Summary cuối cùng** (tổng hợp tất cả answers) — mỗi Q trả lời riêng là đủ cho bước 1
