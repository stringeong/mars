type IconName = 'dashboard' | 'workflow' | 'workers' | 'desktop' | 'files' | 'history' | 'settings' | 'edit' | 'panel' | 'trash' | 'laptop' | 'more' | 'copy' | 'play' | 'check' | 'info' | 'users' | 'download' | 'logout' | 'undo' | 'expand' | 'shrink' | 'arrange' | 'arrow-right'

const paths: Record<IconName, JSX.Element> = {
  dashboard: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,
  workflow: <><circle cx="12" cy="12" r="9"/><path d="M12 8v8M8 12h8"/></>,
  workers: <><rect x="4" y="8" width="16" height="12" rx="2"/><path d="M12 8V4H8M2 14h2M20 14h2M15 13v2M9 13v2"/></>,
  desktop: <><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M8 9h8M8 13h5M9 19v2M15 19v2"/></>,
  files: <><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></>,
  history: <><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5M12 7v5l4 2"/></>,
  edit: <><path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13.5 6.5l4 4"/></>,
  laptop: <><rect x="4" y="5" width="16" height="10" rx="2"/><path d="M2 19h20"/></>,
  more: <><circle cx="5" cy="12" r="1.2"/><circle cx="12" cy="12" r="1.2"/><circle cx="19" cy="12" r="1.2"/></>,
  copy: <><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/></>,
  play: <><path d="M7 5l12 7-12 7z"/></>,
  check: <><path d="M9 11l3 3 8-8"/><path d="M20 12v6a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h9"/></>,
  info: <><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/></>,
  users: <><circle cx="9" cy="8" r="3.5"/><path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7M18 14c2 .8 3 2.8 3 6"/></>,
  download: <><path d="M12 4v11M7 10l5 5 5-5"/><path d="M5 20h14"/></>,
  logout: <><path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3"/><path d="M10 16l-4-4 4-4M6 12h10"/></>,
  undo: <><path d="M9 14L4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/></>,
  expand: <><path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/></>,
  shrink: <><path d="M4 14h6v6M20 10h-6V4M14 10l7-7M3 21l7-7"/></>,
  arrange: <><rect x="3" y="4" width="6" height="5" rx="1"/><rect x="15" y="4" width="6" height="5" rx="1"/><rect x="9" y="15" width="6" height="5" rx="1"/><path d="M6 9v3h12V9M12 12v3"/></>,
  'arrow-right': <><path d="M5 12h14M13 6l6 6-6 6"/></>,
  trash: <><path d="M4 7h16M10 11v6M14 11v6"/><path d="M6 7l1 13h10l1-13M9 7V4h6v3"/></>,
  panel: <><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/></>,
  settings: <><path d="M9.39 4.86 L9.70 2.99 L14.30 2.99 L14.61 4.86 L16.88 6.17 L18.65 5.50 L20.95 9.49 L19.49 10.69 L19.49 13.31 L20.95 14.51 L18.65 18.50 L16.88 17.83 L14.61 19.14 L14.30 21.01 L9.70 21.01 L9.39 19.14 L7.12 17.83 L5.35 18.50 L3.05 14.51 L4.51 13.31 L4.51 10.69 L3.05 9.49 L5.35 5.50 L7.12 6.17Z"/><circle cx="12" cy="12" r="3.2"/></>,
}

export default function AppIcon({ name }: { name: IconName }) {
  return <svg className="app-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>
}
