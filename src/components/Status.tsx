export function Loading({ text }: { text: string }) {
  return (
    <div className="loading" role="status">
      <span className="spinner" />
      <span>{text}</span>
    </div>
  );
}

export function ErrorNote({ message }: { message: string }) {
  return message ? (
    <p className="error" role="alert">
      {message}
    </p>
  ) : null;
}
