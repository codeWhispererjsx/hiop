type BrandLogoProps = { className?: string; compact?: boolean };

export default function BrandLogo({ className = "", compact = false }: BrandLogoProps) {
  return <span className={`brand-logo ${compact ? "brand-logo--compact" : ""} ${className}`.trim()}>
    <img className="brand-logo-light" src="/hospitality-it-ops-wordmark-light-transparent.png" alt="Hospitality IT Ops" />
    <img className="brand-logo-dark" src="/hospitality-it-ops-wordmark-dark-transparent.png" alt="" aria-hidden="true" />
  </span>;
}
