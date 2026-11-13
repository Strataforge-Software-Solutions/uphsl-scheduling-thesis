import { useEffect } from "react";
import { createPortal } from "react-dom";

/* Keep modal layers attached to the viewport instead of transformed/scrolling page content. */
export default function ModalPortal({ children }) {
  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    const previousRootOverflow = document.documentElement.style.overflow;
    document.body.style.overflow = "hidden";
    document.documentElement.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
      document.documentElement.style.overflow = previousRootOverflow;
    };
  }, []);

  return createPortal(children, document.body);
}
