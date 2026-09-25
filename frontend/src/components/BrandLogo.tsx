type BrandLogoProps = { className?: string; compact?: boolean; logo?: string | null; organizationName?: string };

export default function BrandLogo({ className = "", compact = false, logo, organizationName = "Hospitality IT Ops" }: BrandLogoProps) {
  const asset = (name: string) => `${import.meta.env.BASE_URL}${name}`;
  return <span className={`brand-logo ${compact ? "brand-logo--compact" : ""} ${className}`.trim()}>
    {logo ? <img className="brand-logo-custom" src={logo} alt={organizationName} /> : <>
      <img className="brand-logo-light" src={asset("hospitality-it-ops-wordmark-light-transparent.png")} alt="Hospitality IT Ops" />
      <img className="brand-logo-dark" src={asset("hospitality-it-ops-wordmark-dark-transparent.png")} alt="" aria-hidden="true" />
    </>}
  </span>;
}
