import type { ReactNode } from "react";

export function PageTitle({ eyebrow, title, copy, action }: { eyebrow: string; title: string; copy: string; action?: ReactNode }) {
  return <header className="page-title">
    <div className="page-title-copy">
      <p className="page-kicker">{eyebrow}</p>
      <h1>{title}</h1>
      <p>{copy}</p>
    </div>
    {action && <div className="page-title-actions">{action}</div>}
  </header>;
}
