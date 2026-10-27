import { useState } from 'react';
import FrameCard from '../components/FrameCard.jsx';
import { Heading, SectionHeading, SearchInput, Select } from '../components/Shared.jsx';
import { frames } from '../data/demo.js';

export default function FrameLibrary({ onFrame }) {
  const [query, setQuery] = useState('');
  const [type, setType] = useState('All frames');
  const [date, setDate] = useState('All dates');
  const found = frames.filter(frame => (type === 'All frames' || frame.type === type)
    && (date === 'All dates' || frame.date === date)
    && [frame.title, frame.caption, frame.ocr, ...frame.tags].join(' ').toLowerCase().includes(query.trim().toLowerCase()));
  return <>
    <Heading title="A memory you can explore." subtitle="Browse the moments selected from your sample sessions." />
    <div className="toolbar"><SearchInput value={query} onChange={setQuery} label="Search sample frames" placeholder="Search scenes, objects or recognized text…" /><Select label="Filter frames" value={type} onChange={setType} options={['All frames', 'Text detected', 'Objects detected', 'Scene captured']} /><Select label="Filter frames by date" value={date} onChange={setDate} options={['All dates', 'Today', 'Yesterday']} /></div>
    <div aria-live="polite"><SectionHeading title={`${found.length} ${found.length === 1 ? 'moment' : 'moments'}`} subtitle="Demo library · illustrated scene thumbnails" /></div>
    <div className="frames large-frames">{found.map(frame => <FrameCard key={frame.id} frame={frame} onSelect={onFrame} />)}</div>
    {found.length === 0 && <div className="panel empty">No moments match your search. Try “door”, “cup” or “EXIT”.</div>}
  </>;
}
