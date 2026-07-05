import { AppLayout } from './components/AppLayout'
import { BackendStatusPanel } from './components/BackendStatusPanel'
import { PreviewVisibilityProvider } from './context/PreviewVisibilityContext'

function App() {
  return (
    <PreviewVisibilityProvider>
      <AppLayout>
        <BackendStatusPanel />
      </AppLayout>
    </PreviewVisibilityProvider>
  )
}

export default App
