import Icon from './Icon.jsx';

export function Heading({ title, subtitle, children }) {
  return <div className="page-heading"><div><span className="eyebrow">YOUR WORLD, IN PERSPECTIVE</span><h1>{title}</h1><p>{subtitle}</p></div><div className="heading-actions">{children}</div></div>;
}

export function SectionHeading({ title, subtitle, link, page }) {
  return <div className="section-heading"><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>{link && <a className="text-link" href={`#${page}`}>{link}<Icon name="arrow" /></a>}</div>;
}

export function SearchInput({ value, onChange, label, placeholder }) {
  return <label className="search-wrap"><Icon name="search" /><input type="search" value={value} onChange={event => onChange(event.target.value)} aria-label={label} placeholder={placeholder} /></label>;
}

export function Select({ label, value, onChange, options }) {
  return <select aria-label={label} value={value} onChange={event => onChange(event.target.value)}>{options.map(option => <option key={option}>{option}</option>)}</select>;
}
