/* ════════════════════════════════════════════════════════════════════════════
   Kiểu dữ liệu cho các hàng (row) trả về từ PostgreSQL.
   Mục tiêu: thay `query<any>` bằng `query<KiểuCụThể>` để có gợi ý + bắt lỗi
   sai tên cột lúc biên dịch — KHÔNG đổi SQL, chỉ thêm an toàn kiểu.
   Mỗi interface mô tả ĐÚNG các cột mà câu SELECT tương ứng trả về.
   ════════════════════════════════════════════════════════════════════════════ */

export type Role = "user" | "admin";

// Hàng đếm: SELECT count(*)::int AS n
export interface CountRow {
  n: number;
}

// Thẻ người dùng rút gọn (avatar partial · danh sách bạn bè · lời mời).
// `intro` chỉ có mặt ở truy vấn lời mời kết bạn.
export interface UserCard {
  id: number;
  name: string;
  has_avatar: boolean;
  intro?: string | null;
  online?: boolean;             // presence: gắn ở runtime (isOnline)
  last_seen?: Date | string | null;
}

// Hồ sơ công khai: SELECT id,name,email,role,created_at,(avatar IS NOT NULL) AS has_avatar
export interface ProfileRow {
  id: number;
  name: string;
  email: string;
  role: Role;
  created_at: Date;
  has_avatar: boolean;
}

// Đọc blob để tải/stream (attachment · ảnh/tài liệu bài viết · media tin nhắn).
export interface BlobRow {
  filename?: string | null;
  mime: string | null;
  data: Buffer | null;
  doc_original?: string | null;
}

// ── Tin nhắn trực tiếp (theo DM_COLS) + bản xem trước sau enrichMessages ───────
export interface DmSharedPost {
  id: number;
  content: string;
  author: string;
  has_image: boolean;
  has_video: boolean;
  has_doc: boolean;
}
export interface DmSharedCourse {
  item_id: number;
  title: string;
  type: string;
  category: string;
}
export interface DmRow {
  id: number;
  sender_id: number;
  content: string;
  created_at: Date;
  read_at: Date | null;         // realtime: thời điểm người nhận đã đọc ("đã xem")
  has_image: boolean;
  has_video: boolean;
  has_doc: boolean;
  doc_original: string | null;
  shared_post_id: number | null;
  shared_course_id: number | null;
  post?: DmSharedPost | null;     // gắn thêm bởi enrichMessages
  course?: DmSharedCourse | null; // gắn thêm bởi enrichMessages
}
// Đọc media của 1 tin nhắn (kèm 2 đầu để kiểm tra quyền).
export interface DmMediaRow {
  sender_id: number;
  recipient_id: number;
  data: Buffer | null;
  mime: string | null;
  doc_original: string | null;
}

// ── Bài viết cộng đồng (fetchPosts) ───────────────────────────────────────────
export interface CommentRow {
  id: number;
  post_id: number;
  content: string;
  created_at: Date;
  author: string;
}
export interface PostOrigin {
  id: number;
  content: string;
  doc_original: string | null;
  author: string;
  has_image: boolean;
  has_video: boolean;
  has_doc: boolean;
}
export interface PostRow {
  id: number;
  content: string;
  created_at: Date;
  user_id: number;
  shared_from: number | null;
  author: string;
  author_avatar: boolean;
  has_image: boolean;
  has_video: boolean;
  has_doc: boolean;
  doc_original: string | null;
  likes: number;
  liked: boolean;
  comments: CommentRow[];     // gắn thêm sau truy vấn
  origin: PostOrigin | null;  // gắn thêm sau truy vấn (nếu là bài share)
}

// ── Bài học video trong khóa học ──────────────────────────────────────────────
export interface LessonRow {
  id: number;
  title: string;
  youtube_id: string;
  added_by: number | null;
  done: boolean;
}

// ── Bảng quản trị ─────────────────────────────────────────────────────────────
export interface AdminStats {
  users: number;
  courses: number;
  enrollments: number;
  conversations: number;
  messages: number;
  posts: number;
  comments: number;
  attachments: number;
}
export interface AdminFileRow {
  kind: "attachment" | "post-image" | "post-doc";
  id: number;
  name: string | null;
  mime: string | null;
  bytes: number | null;
  uploader: string | null;
  created_at: Date;
  context: string;
}
export interface AdminUserRow {
  id: number;
  name: string;
  email: string;
  role: Role;
  created_at: Date;
}
export interface AdminPostRow {
  id: number;
  author: string;
  content: string;
  created_at: Date;
  img: boolean;
  doc: string | null;
}
