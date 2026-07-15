import Modal from "./Modal";

export function ConfirmationModal({ title, children, confirmLabel, busyLabel, busy, error, onCancel, onConfirm }: {
  title: string;
  children: React.ReactNode;
  confirmLabel: string;
  busyLabel: string;
  busy: boolean;
  error?: string;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return <Modal title={title} onClose={() => !busy && onCancel()}>
    <div className="confirmation-content">
      {children}
      {error && <div className="form-error" role="alert">{error}</div>}
      <footer>
        <button type="button" className="secondary-action" disabled={busy} onClick={onCancel}>Cancel</button>
        <button type="button" className="danger-action" disabled={busy} onClick={onConfirm}>{busy ? busyLabel : confirmLabel}</button>
      </footer>
    </div>
  </Modal>;
}
