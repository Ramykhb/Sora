export default function Brand({ compact = false }) {
  return <a className={`brand${compact ? ' compact-brand' : ''}`} href="#overview" aria-label="Sora home"><img className="brand-logo" src="/brand/sora-logo.svg" alt="" width="38" height="38" /><span>sora</span></a>;
}
