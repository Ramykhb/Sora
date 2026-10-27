import { useState } from 'react';
import Icon from '../components/Icon.jsx';
import { Heading, SearchInput, Select } from '../components/Shared.jsx';
import { frames, questions } from '../data/demo.js';
import scene from '../../assets/scene.svg';

export default function Conversations({ onFrame }) {
  const [query, setQuery] = useState('');
  const [language, setLanguage] = useState('All languages');
  const found = questions.filter(question => (language === 'All languages' || question.language === language)
    && `${question.q} ${question.a}`.toLowerCase().includes(query.trim().toLowerCase()));
  return <>
    <Heading title="Every question has a story." subtitle="Review sample answers and the moments behind them." />
    <div className="toolbar"><SearchInput value={query} onChange={setQuery} label="Search sample conversations" placeholder="Find a question or answer…" /><Select label="Filter conversation language" value={language} onChange={setLanguage} options={['All languages', 'English', 'Français']} /></div>
    {found.map(question => <article className="conversation-card" key={question.q}><div className="conversation-meta"><span>{question.time} · {question.language} · {question.scope}</span><span className={`pill ${question.status === 'Uncertain' ? 'amber' : ''}`}>{question.status}</span></div><h2>{question.q}</h2><p>{question.a}</p><div className="evidence"><img src={scene} alt="" /><span>1 supporting frame · {frames[question.frame].id}</span><button className="text-link" onClick={() => onFrame(frames[question.frame])}>View evidence <Icon name="arrow" /></button></div></article>)}
    {found.length === 0 && <div className="panel empty" role="status">No conversations match your search.</div>}
  </>;
}
