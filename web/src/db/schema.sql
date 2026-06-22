-- Schema nền tảng học tập CNTT. Chạy idempotent (IF NOT EXISTS) qua migrate.ts.

CREATE EXTENSION IF NOT EXISTS citext;

CREATE TABLE IF NOT EXISTS users (
  id            SERIAL PRIMARY KEY,
  email         CITEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  name          TEXT NOT NULL,
  role          TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Catalog đồng bộ từ data/it_learning_items.csv (nguồn chính trong Postgres).
CREATE TABLE IF NOT EXISTS courses (
  item_id     INTEGER PRIMARY KEY,
  title       TEXT NOT NULL,
  type        TEXT,
  level       TEXT,
  description TEXT,
  category    TEXT,
  topics      TEXT,
  instructor  TEXT,
  platform    TEXT,
  link        TEXT
);

CREATE INDEX IF NOT EXISTS idx_courses_category ON courses (category);
CREATE INDEX IF NOT EXISTS idx_courses_type     ON courses (type);

-- Khóa học người dùng đã lưu / đang học / hoàn thành.
CREATE TABLE IF NOT EXISTS enrollments (
  id         SERIAL PRIMARY KEY,
  user_id    INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  course_id  INTEGER NOT NULL REFERENCES courses (item_id) ON DELETE CASCADE,
  status     TEXT NOT NULL DEFAULT 'saved' CHECK (status IN ('saved', 'in_progress', 'completed')),
  progress   INTEGER NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, course_id)
);

CREATE INDEX IF NOT EXISTS idx_enrollments_user ON enrollments (user_id);

-- Lịch sử hội thoại chatbot (mỗi user nhiều cuộc trò chuyện).
CREATE TABLE IF NOT EXISTS conversations (
  id         SERIAL PRIMARY KEY,
  user_id    INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  title      TEXT NOT NULL DEFAULT 'Cuộc trò chuyện mới',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations (user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS messages (
  id              SERIAL PRIMARY KEY,
  conversation_id INTEGER NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
  role            TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
  content         TEXT NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages (conversation_id, id);

-- Tài liệu người dùng tải lên đính kèm vào một khóa học/tài liệu.
CREATE TABLE IF NOT EXISTS attachments (
  id          SERIAL PRIMARY KEY,
  course_id   INTEGER NOT NULL REFERENCES courses (item_id) ON DELETE CASCADE,
  user_id     INTEGER REFERENCES users (id) ON DELETE SET NULL,
  filename    TEXT NOT NULL,        -- tên gốc người dùng tải lên
  mime        TEXT,
  size        INTEGER,
  data        BYTEA NOT NULL,       -- NỘI DUNG file lưu thẳng trong PostgreSQL (để deploy đa máy)
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_attachments_course ON attachments (course_id);

-- ── Blog cộng đồng IT: bài viết · thích · bình luận ───────────────────────────
CREATE TABLE IF NOT EXISTS posts (
  id           SERIAL PRIMARY KEY,
  user_id      INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  content      TEXT NOT NULL DEFAULT '',
  image_data   BYTEA,                -- ảnh đính kèm (lưu thẳng trong PostgreSQL)
  image_mime   TEXT,
  doc_data     BYTEA,                -- tài liệu đính kèm (lưu thẳng trong PostgreSQL)
  doc_mime     TEXT,
  doc_original TEXT,                 -- tên gốc tài liệu (để hiển thị/tải xuống)
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_posts_created ON posts (created_at DESC);

CREATE TABLE IF NOT EXISTS post_likes (
  post_id INTEGER NOT NULL REFERENCES posts (id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  PRIMARY KEY (post_id, user_id)
);

CREATE TABLE IF NOT EXISTS post_comments (
  id         SERIAL PRIMARY KEY,
  post_id    INTEGER NOT NULL REFERENCES posts (id) ON DELETE CASCADE,
  user_id    INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  content    TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_comments_post ON post_comments (post_id, id);

-- Nội dung trích xuất từ file (PDF/DOCX/Excel) để xem inline + nạp vào dataset.
-- ALTER idempotent: áp dụng cho cả DB cũ lẫn mới.
ALTER TABLE attachments ADD COLUMN IF NOT EXISTS extracted_text TEXT;

-- ── Mạng xã hội: avatar · video bài viết · chia sẻ · kết bạn · nhắn tin ────────
ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_data BYTEA;
ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_mime TEXT;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS video_data BYTEA;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS video_mime TEXT;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS shared_from INTEGER REFERENCES posts (id) ON DELETE SET NULL;

CREATE TABLE IF NOT EXISTS friendships (
  id           SERIAL PRIMARY KEY,
  requester_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  addressee_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  status       TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted')),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (requester_id, addressee_id),
  CHECK (requester_id <> addressee_id)
);
CREATE INDEX IF NOT EXISTS idx_friend_addressee ON friendships (addressee_id, status);

-- Lời giới thiệu kèm lời mời kết bạn (để người nhận biết lý do mà chấp nhận).
ALTER TABLE friendships ADD COLUMN IF NOT EXISTS intro TEXT;

CREATE TABLE IF NOT EXISTS direct_messages (
  id           SERIAL PRIMARY KEY,
  sender_id    INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  recipient_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  content      TEXT NOT NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_dm_thread ON direct_messages (sender_id, recipient_id, id);

-- Tin nhắn đính kèm media + chia sẻ bài viết / khóa học vào đoạn chat (lưu thẳng trong PostgreSQL).
ALTER TABLE direct_messages ADD COLUMN IF NOT EXISTS image_data  BYTEA;
ALTER TABLE direct_messages ADD COLUMN IF NOT EXISTS image_mime  TEXT;
ALTER TABLE direct_messages ADD COLUMN IF NOT EXISTS video_data  BYTEA;
ALTER TABLE direct_messages ADD COLUMN IF NOT EXISTS video_mime  TEXT;
ALTER TABLE direct_messages ADD COLUMN IF NOT EXISTS doc_data    BYTEA;
ALTER TABLE direct_messages ADD COLUMN IF NOT EXISTS doc_mime    TEXT;
ALTER TABLE direct_messages ADD COLUMN IF NOT EXISTS doc_original TEXT;
ALTER TABLE direct_messages ADD COLUMN IF NOT EXISTS shared_post_id   INTEGER REFERENCES posts (id) ON DELETE SET NULL;
ALTER TABLE direct_messages ADD COLUMN IF NOT EXISTS shared_course_id INTEGER REFERENCES courses (item_id) ON DELETE SET NULL;
ALTER TABLE direct_messages ALTER COLUMN content SET DEFAULT '';

-- Realtime: thời điểm người nhận đã đọc tin (cho "đã xem") + lần online gần nhất của user (presence).
ALTER TABLE direct_messages ADD COLUMN IF NOT EXISTS read_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_seen TIMESTAMPTZ;
-- Lọc nhanh tin chưa đọc theo người nhận (đánh dấu đã xem).
CREATE INDEX IF NOT EXISTS idx_dm_unread ON direct_messages (recipient_id, sender_id) WHERE read_at IS NULL;

-- ── Bài học video (YouTube) trong khóa học + tiến độ theo từng bài ─────────────
CREATE TABLE IF NOT EXISTS lessons (
  id         SERIAL PRIMARY KEY,
  course_id  INTEGER NOT NULL REFERENCES courses (item_id) ON DELETE CASCADE,
  title      TEXT NOT NULL,
  youtube_id TEXT NOT NULL,
  added_by   INTEGER REFERENCES users (id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_lessons_course ON lessons (course_id, id);

CREATE TABLE IF NOT EXISTS lesson_progress (
  user_id      INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  lesson_id    INTEGER NOT NULL REFERENCES lessons (id) ON DELETE CASCADE,
  completed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, lesson_id)
);

-- ── Duyệt đóng góp: admin thêm trực tiếp = approved; user đóng góp = chờ duyệt ──
-- approved=true cho dữ liệu cũ (grandfather) và mục do admin tạo; false = chờ admin duyệt.
ALTER TABLE lessons     ADD COLUMN IF NOT EXISTS approved BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE attachments ADD COLUMN IF NOT EXISTS approved BOOLEAN NOT NULL DEFAULT true;
CREATE INDEX IF NOT EXISTS idx_lessons_pending     ON lessons (course_id)     WHERE approved = false;
CREATE INDEX IF NOT EXISTS idx_attachments_pending ON attachments (course_id) WHERE approved = false;
