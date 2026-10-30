import { initials } from "../api.js";
import { GRADS, useAvatarLook } from "../avatar.js";

/** The member's picture if they added one, else initials on their chosen colour. */
export default function Avatar({ m, cls = "", tag: Tag = "span", ...rest }) {
  const { photo, colour } = useAvatarLook(m ? m.id : "");
  const style = photo
    ? { backgroundImage: `url(${photo})`, backgroundSize: "cover", backgroundPosition: "center", color: "transparent", border: 0 }
    : colour != null ? { background: GRADS[colour] || undefined, color: "#fff", border: 0 } : undefined;
  return <Tag className={("avatar " + cls).trim()} style={style} {...rest}>{m ? initials(m.name) : "?"}</Tag>;
}
