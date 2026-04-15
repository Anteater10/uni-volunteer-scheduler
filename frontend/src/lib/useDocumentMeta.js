import { useEffect } from "react";

function upsertMeta(name, content, attr = "name") {
  if (!content) return;
  let el = document.head.querySelector(`meta[${attr}="${name}"]`);
  if (!el) {
    el = document.createElement("meta");
    el.setAttribute(attr, name);
    document.head.appendChild(el);
  }
  el.setAttribute("content", content);
}

export function useDocumentMeta({
  title,
  description,
  ogTitle,
  ogDescription,
  ogType = "website",
}) {
  useEffect(() => {
    if (title) document.title = title;
    upsertMeta("description", description);
    upsertMeta("og:title", ogTitle ?? title, "property");
    upsertMeta("og:description", ogDescription ?? description, "property");
    upsertMeta("og:type", ogType, "property");
  }, [title, description, ogTitle, ogDescription, ogType]);
}
