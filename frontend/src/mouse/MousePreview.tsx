export function MousePreview({ rotation }: { rotation: number }) {
  return <svg className="mouse-illustration" viewBox="0 0 360 330" role="img" aria-label={`Mouse schematic; draft sensor rotation ${rotation} degrees`}>
    <path d="M180 25C113 25 94 78 94 148l-9 76c-4 49 35 78 95 78s99-29 95-78l-9-76c0-70-19-123-86-123Z" fill="#172237" stroke="#586782" strokeWidth="2" />
    <path d="M180 26v113M96 136c52 16 116 16 168 0" fill="none" stroke="#586782" strokeWidth="2" />
    <rect x="169" y="58" width="22" height="44" rx="10" fill="#9c91f7" />
    <path d="M120 213h120M180 153v119" stroke="#394b69" strokeDasharray="5 5" />
    <g transform={`rotate(${rotation} 180 213)`}><path d="M180 168v90m-18-72 18-18 18 18" fill="none" stroke="#b9b1ff" strokeWidth="3" /><circle cx="180" cy="213" r="12" fill="#222f47" stroke="#b9b1ff" strokeWidth="2" /></g>
    <text x="180" y="321" textAnchor="middle" fill="#aab9d1" fontSize="11">Schematic · local preview</text>
  </svg>;
}
