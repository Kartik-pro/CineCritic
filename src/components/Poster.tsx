export function Poster({ src, title, className = "" }: { src: string; title: string; className?: string }) {
  return src ? (
    <img className={`poster ${className}`} src={src} alt={`${title} poster`} loading="lazy" />
  ) : (
    <div className={`poster poster-empty ${className}`} aria-hidden="true">
      {title.slice(0, 1)}
    </div>
  );
}
