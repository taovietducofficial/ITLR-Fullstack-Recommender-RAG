import { query } from "../db/pool";
import { PostRow, PostOrigin, CommentRow } from "../db/types";

// Lấy danh sách bài viết (kèm tác giả, avatar, media, số like/comment, bài gốc nếu là share).
// meId: user hiện tại (để biết đã like chưa). filterUserId: chỉ lấy bài của 1 user (profile).
// postId: chỉ lấy đúng 1 bài (cho trang xem bài riêng /blog/:id — bài chia sẻ trong tin nhắn).
export async function fetchPosts(meId: number, filterUserId?: number, postId?: number): Promise<PostRow[]> {
  const params: unknown[] = [meId];
  let where = "";
  if (postId != null) { params.push(postId); where = "WHERE p.id = $2"; }
  else if (filterUserId != null) { params.push(filterUserId); where = "WHERE p.user_id = $2"; }

  const posts = await query<PostRow>(
    `SELECT p.id, p.content, p.created_at, p.user_id, p.shared_from,
            u.name AS author, (u.avatar_data IS NOT NULL) AS author_avatar,
            (p.image_data IS NOT NULL) AS has_image,
            (p.video_data IS NOT NULL) AS has_video,
            (p.doc_data IS NOT NULL)   AS has_doc, p.doc_original,
            (SELECT count(*)::int FROM post_likes l WHERE l.post_id = p.id) AS likes,
            EXISTS(SELECT 1 FROM post_likes l WHERE l.post_id = p.id AND l.user_id = $1) AS liked
       FROM posts p JOIN users u ON u.id = p.user_id
       ${where}
      ORDER BY p.id DESC LIMIT 100`,
    params
  );
  if (!posts.length) return posts;

  // Bài gốc cho các bài share
  const sharedIds = posts.filter((p) => p.shared_from).map((p) => p.shared_from);
  const origins: Record<number, PostOrigin> = {};
  if (sharedIds.length) {
    const os = await query<PostOrigin>(
      `SELECT p.id, p.content, p.doc_original, u.name AS author,
              (p.image_data IS NOT NULL) AS has_image, (p.video_data IS NOT NULL) AS has_video, (p.doc_data IS NOT NULL) AS has_doc
         FROM posts p JOIN users u ON u.id = p.user_id WHERE p.id = ANY($1::int[])`,
      [sharedIds]
    );
    os.forEach((o) => { origins[o.id] = o; });
  }

  // Bình luận của các bài
  const ids = posts.map((p) => p.id);
  const comments = await query<CommentRow>(
    `SELECT c.id, c.post_id, c.content, c.created_at, u.name AS author
       FROM post_comments c JOIN users u ON u.id = c.user_id
      WHERE c.post_id = ANY($1::int[]) ORDER BY c.id`,
    [ids]
  );
  const byPost: Record<number, CommentRow[]> = {};
  comments.forEach((c) => { (byPost[c.post_id] ||= []).push(c); });

  posts.forEach((p) => {
    p.comments = byPost[p.id] || [];
    p.origin = p.shared_from ? origins[p.shared_from] || null : null;
  });
  return posts;
}
