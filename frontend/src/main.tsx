import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/theme.css'
import './styles/global.css'
import './i18n'
import App from './App.tsx'
import { syncCollageAspect } from './utils/collageAspect'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

void syncCollageAspect()

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js')
}
