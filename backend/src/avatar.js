import { useSyncExternalStore } from "react";

// A member's own picture (and colour choice) lives in this browser. It is resized to a small square first.
export const GRADS = [
  "linear-gradient(135deg,#d8294f,#ff7a93)", "linear-gradient(135deg,#141111,#4a3f3f)", "linear-gradient(135deg,#f59e0b,#ef4444)",
  "linear-gradient(135deg,#7c3aed,#d8294f)", "linear-gradient(135deg,#8b8381,#c9bfbc)", "linear-gradient(135deg,#be123c,#7f1d1d)",
];
const subs = new Set();
const key = (kind, id) => `wp_${kind}_${id}`;
const read = (k) => { try { return localStorage.getItem(k); } catch { return null; } };
const write = (k, v) => {
  try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch { /* private mode: fine */ }
  subs.forEach((f) => f());
};
const subscribe = (f) => { subs.add(f); return () => subs.delete(f); };

export const setPhoto = (id, dataUrl) => write(key("photo", id), dataUrl);
export const setColour = (id, i) => write(key("av", id), i == null ? null : String(i));

/** { photo: dataURL | null, colour: number | null } for one member, live. */
export function useAvatarLook(id) {
  const photo = useSyncExternalStore(subscribe, () => read(key("photo", id)));
  const colour = useSyncExternalStore(subscribe, () => read(key("av", id)));
  return { photo, colour: colour == null ? null : Number(colour) };
}

/** Centre-crop any picture to a 192px square JPEG (about 10 KB). */
export function fileToAvatar(file) {
  return new Promise((resolve, reject) => {
    if (!file || !file.type.startsWith("image/")) return reject(new Error("Please choose an image file"));
    if (file.size > 12 * 1024 * 1024) return reject(new Error("That picture is too large (max 12 MB)"));
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      const n = 192, s = Math.min(img.width, img.height);
      const c = document.createElement("canvas");
      c.width = c.height = n;
      c.getContext("2d").drawImage(img, (img.width - s) / 2, (img.height - s) / 2, s, s, 0, 0, n, n);
      URL.revokeObjectURL(url);
      resolve(c.toDataURL("image/jpeg", 0.85));
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("That file could not be read as a picture")); };
    img.src = url;
  });
}