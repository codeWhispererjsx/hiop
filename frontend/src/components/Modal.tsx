import type { ReactNode } from "react";
import { Icon } from "./Icon";
export default function Modal({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  return <div className="modal-backdrop" role="presentation" onMouseDown={onClose}><section className="modal" role="dialog" aria-modal="true" aria-label={title} onMouseDown={e => e.stopPropagation()}><header><h2>{title}</h2><button className="icon-button" onClick={onClose} aria-label="Close"><Icon name="close"/></button></header>{children}</section></div>;
}
