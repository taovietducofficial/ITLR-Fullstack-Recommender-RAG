export type Role = "user" | "admin";

export interface CountRow {
  n: number;
}

export interface UserCard {
  id: number;
  name: string;
  has_avatar: boolean;
  intro?: string | null;
  online?: boolean;
  last_seen?: Date | string | null;
}

export interface ProfileRow {
  id: number;
  name: string;
  email: string;
  role: Role;
  created_at: Date;
  has_avatar: boolean;
}

export interface BlobRow {
  filename?: string | null;
  mime: string | null;
  data: Buffer | null;
  doc_original?: string | null;
}

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
  read_at: Date | null;
  has_image: boolean;
  has_video: boolean;
  has_doc: boolean;
  doc_original: string | null;
  shared_post_id: number | null;
  shared_course_id: number | null;
  post?: DmSharedPost | null;
  course?: DmSharedCourse | null;
}
export interface DmMediaRow {
  sender_id: number;
  recipient_id: number;
  data: Buffer | null;
  mime: string | null;
  doc_original: string | null;
}

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
  comments: CommentRow[];
  origin: PostOrigin | null;
}

export interface LessonRow {
  id: number;
  title: string;
  youtube_id: string;
  added_by: number | null;
  done: boolean;
}

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
