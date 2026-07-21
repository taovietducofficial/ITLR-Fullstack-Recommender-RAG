import MarkdownIt from "markdown-it";

const md = new MarkdownIt({ html: false, breaks: true, linkify: true });

export function renderMd(src: string): string {
  return md.render(src || "");
}

export function googleRefs(query: string): { label: string; url: string }[] {
  const t = (query || "").trim().slice(0, 120);
  if (!t) return [];
  const g = (q: string) => "https://www.google.com/search?q=" + encodeURIComponent(q);
  return [
    { label: `Tìm "${t}" trên Google`, url: g(t) },
    { label: "Hướng dẫn & lộ trình học", url: g(t + " hướng dẫn lộ trình học") },
    { label: "Tài liệu chính thức (docs)", url: g(t + " tài liệu chính thức documentation") },
  ];
}
